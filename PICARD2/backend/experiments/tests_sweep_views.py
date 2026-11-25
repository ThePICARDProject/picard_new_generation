import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from datasets.models import CSVDataset
from scripts.models import Script

from .models import PUBLIC, SparkExperiment, SweepBatch
from .tasks import run_db_script


MANIFESTS = Path(__file__).resolve().parents[1] / 'scripts' / 'manifests'
MLRF = json.loads((MANIFESTS / 'supervisedmlrf.json').read_text())
DELAY = 'experiments.sweep_views.run_db_script.delay'


class SweepViewTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        override = override_settings(MEDIA_ROOT=self.media_root, SWEEP_MAX_EXPERIMENTS=100)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, self.media_root)

        self.user = User.objects.create_user(username='sweeper')
        self.other = User.objects.create_user(username='someone-else')
        files = Path(self.media_root) / 'files'
        (files / 'scripts').mkdir(parents=True)
        (files / 'datasets').mkdir(parents=True)
        (files / 'scripts' / 'mlrf.jar').write_bytes(b'jar bytes')
        (files / 'datasets' / 'd.csv').write_bytes(b'a,b\n1,0\n')
        self.script = Script.objects.create(
            user=self.user, name='SupervisedMLRF', file_type=Script.JAR, file='files/scripts/mlrf.jar',
            main_class='edu.wvu.rascl.driver.SupervisedMLRF', algorithm_config=MLRF,
        )
        self.dataset = CSVDataset.objects.create(user=self.user, name='d.csv', file='files/datasets/d.csv')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def body(self, **overrides):
        return {
            'name': 'Trees and impurity',
            'script_id': str(self.script.id),
            'dataset_id': str(self.dataset.id),
            'parameters': {'numTrees': [10, 20, 30], 'impurity': ['gini', 'entropy']},
            **overrides,
        }

    def create(self, **overrides):
        with patch(DELAY) as delay:
            response = self.client.post(reverse('sweeps'), self.body(**overrides), format='json')
        return response, delay

    def detail(self, batch_id):
        return self.client.get(reverse('sweep_detail', args=[batch_id])).json()

    def set_status(self, batch_id, statuses):
        runs = SparkExperiment.objects.filter(batch_id=batch_id).order_by('sweep_index')
        for run, status in zip(runs, statuses):
            SparkExperiment.objects.filter(pk=run.pk).update(status=status)

    # Creation -------------------------------------------------------------

    def test_create_makes_ordinary_queued_experiments_and_dispatches_in_order(self):
        response, delay = self.create()
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual((data['total_count'], data['status']), (6, 'Queued'))
        self.assertEqual(data['counts']['Queued'], 6)
        runs = list(SparkExperiment.objects.filter(batch_id=data['id']).order_by('sweep_index'))
        self.assertEqual([run.sweep_index for run in runs], list(range(6)))
        self.assertEqual(runs[1].param_values['impurity'], 'entropy')
        self.assertEqual(runs[0].args, '2 10 gini 5 32 70')
        self.assertTrue(all(run.status == 'Queued' and run.user == self.user for run in runs))
        self.assertEqual([call.args[0] for call in delay.call_args_list], [run.id for run in runs])
        self.assertEqual([run['sweep_index'] for run in data['runs']], list(range(6)))

    def test_creation_records_manifest_definition_and_checksums(self):
        response, _ = self.create()
        batch = SweepBatch.objects.get(id=response.json()['id'])
        self.assertEqual(batch.parameters['manifest'], MLRF)
        self.assertEqual(batch.parameters['definition'], self.body()['parameters'])
        self.assertEqual(batch.parameters['checksums']['script'], hashlib.sha256(b'jar bytes').hexdigest())
        self.assertEqual(batch.parameters['checksums']['dataset'], hashlib.sha256(b'a,b\n1,0\n').hexdigest())

    def test_tasks_are_published_after_the_rows_are_committed(self):
        seen = []
        with patch(DELAY, side_effect=lambda pk: seen.append(SparkExperiment.objects.get(pk=pk).status)):
            response = self.client.post(reverse('sweeps'), self.body(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(seen, ['Queued'] * 6)

    def test_grid_search_format_and_single_run_sweeps(self):
        response, _ = self.create(parameters={'parameters': {'numTrees': [10, 25, 50]}})
        self.assertEqual(response.json()['total_count'], 3)
        # Fixed values only: one run. (All defaults would duplicate a run above.)
        response, _ = self.create(name='Single run', parameters={'maxDepth': 7})
        self.assertEqual(response.json()['total_count'], 1)
        response, _ = self.create(name='Defaults only', parameters={})
        self.assertEqual(response.status_code, 409)

    def test_invalid_definitions_and_requests_are_rejected_without_writes(self):
        cases = [
            (self.body(parameters={'numTrees': [0]}), 400),
            (self.body(parameters={'unknown': [1]}), 400),
            (self.body(name=''), 400),
            (self.body(name='x' * 121), 400),
            (self.body(script_id=''), 400),
            (self.body(script_id='not-a-uuid'), 404),
        ]
        for body, status in cases:
            with self.subTest(body=body), patch(DELAY) as delay:
                response = self.client.post(reverse('sweeps'), body, format='json')
                self.assertEqual(response.status_code, status)
                delay.assert_not_called()
        self.assertFalse(SweepBatch.objects.exists())
        response = self.client.post(reverse('sweeps'), self.body(parameters={'numTrees': [0]}), format='json')
        self.assertIn('numTrees', response.json()['errors'])

    def test_size_limit(self):
        with override_settings(SWEEP_MAX_EXPERIMENTS=5):
            response, delay = self.create()
        self.assertEqual(response.status_code, 400)
        self.assertIn('limit is 5', response.json()['error'])
        delay.assert_not_called()

    def test_algorithms_without_a_manifest_cannot_be_swept(self):
        self.script.algorithm_config = None
        self.script.save()
        response, _ = self.create()
        self.assertEqual(response.status_code, 400)

    def test_duplicate_of_an_active_experiment_rejects_the_whole_sweep(self):
        active = SparkExperiment.objects.create(
            user=self.user, script=self.script, dataset=self.dataset,
            args='2 20 entropy 5 32 70', status='Running',
        )
        preview = self.client.post(reverse('preview_sweep'), self.body(), format='json').json()
        self.assertEqual(preview['duplicate_conflicts'], [{'sweep_index': 3, 'experiment_id': str(active.id)}])
        response, delay = self.create()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['duplicate_conflicts'][0]['sweep_index'], 3)
        delay.assert_not_called()
        self.assertFalse(SweepBatch.objects.exists())

    def test_partial_dispatch_failure_marks_the_rest_failed(self):
        calls = []

        def flaky(pk):
            calls.append(pk)
            if len(calls) > 2:
                raise OperationalError('broker down')

        with patch(DELAY, side_effect=flaky):
            response = self.client.post(reverse('sweeps'), self.body(), format='json')
        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual((data['queued'], data['total']), (2, 6))
        runs = list(SparkExperiment.objects.filter(batch_id=data['sweep_id']).order_by('sweep_index'))
        self.assertEqual([run.status for run in runs], ['Queued'] * 2 + ['Failed'] * 4)
        with runs[5].output.open('r') as output:
            self.assertIn('Not dispatched', output.read())
        # A failed run can be retried through the ordinary run endpoint.
        with patch('experiments.views.run_db_script.delay'):
            retry = self.client.post(reverse('run_experiment', args=[runs[5].id]))
        self.assertEqual(retry.status_code, 200)

    # Preview --------------------------------------------------------------

    def test_preview_counts_without_writing(self):
        with patch(DELAY) as delay:
            response = self.client.post(reverse('preview_sweep'), self.body(), format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data['count'], data['max_experiments']), (6, 100))
        self.assertEqual(data['parameter_order'][:3], ['numClasses', 'numTrees', 'impurity'])
        self.assertEqual(data['combinations'][1], {
            'sweep_index': 1,
            'param_values': {'numClasses': '2', 'numTrees': '10', 'impurity': 'entropy',
                             'maxDepth': '5', 'maxBins': '32', 'percentLabeled': '70'},
        })
        delay.assert_not_called()
        self.assertFalse(SweepBatch.objects.exists())
        self.assertFalse(SparkExperiment.objects.exists())

    # Access control ---------------------------------------------------------

    def test_other_users_sweeps_are_not_found(self):
        response, _ = self.create()
        batch_id = response.json()['id']
        intruder = APIClient()
        intruder.force_authenticate(self.other)
        self.assertEqual(intruder.get(reverse('sweep_detail', args=[batch_id])).status_code, 404)
        self.assertEqual(intruder.post(reverse('cancel_sweep', args=[batch_id])).status_code, 404)
        self.assertEqual(intruder.delete(reverse('sweep_detail', args=[batch_id])).status_code, 404)
        self.assertEqual(intruder.get(reverse('sweeps')).json(), {'sweeps': []})
        with patch(DELAY):
            response = intruder.post(reverse('sweeps'), self.body(), format='json')
        self.assertEqual(response.status_code, 404)

    def test_public_assets_can_be_swept_by_other_users(self):
        Script.objects.filter(pk=self.script.pk).update(access_level=PUBLIC)
        CSVDataset.objects.filter(pk=self.dataset.pk).update(access_level=PUBLIC)
        client = APIClient()
        client.force_authenticate(self.other)
        with patch(DELAY):
            response = client.post(reverse('sweeps'), self.body(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(SweepBatch.objects.get().user, self.other)

    def test_unauthenticated_requests_are_refused(self):
        self.assertIn(APIClient().get(reverse('sweeps')).status_code, (401, 403))

    # Listing and status -----------------------------------------------------

    def test_list_reports_computed_status_and_counts(self):
        first = self.create()[0].json()['id']
        second = self.create(name='Second', parameters={'maxDepth': [1, 2]})[0].json()['id']
        self.set_status(first, ['Success', 'Failed', 'Success', 'Success', 'Success', 'Success'])
        self.set_status(second, ['Running', 'Queued'])
        listing = {item['id']: item for item in self.client.get(reverse('sweeps')).json()['sweeps']}
        self.assertEqual(listing[first]['status'], 'Completed with failures')
        self.assertEqual(listing[first]['counts']['Failed'], 1)
        self.assertEqual(listing[second]['status'], 'Running')
        self.assertEqual(list(listing), [second, first])

    def test_standalone_experiment_list_includes_batch_fields(self):
        batch_id = self.create()[0].json()['id']
        items = self.client.get(reverse('list_experiments')).json()
        self.assertEqual({item['batch_id'] for item in items}, {batch_id})
        self.assertEqual(sorted(item['sweep_index'] for item in items), list(range(6)))

    # Cancellation -----------------------------------------------------------

    def test_cancel_before_any_run_starts(self):
        batch_id = self.create()[0].json()['id']
        response = self.client.post(reverse('cancel_sweep', args=[batch_id]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual((data['cancelled'], data['status'], data['counts']['Cancelled']), (6, 'Cancelled', 6))
        self.assertTrue(data['cancel_requested'])

    def test_cancel_during_a_run_leaves_running_and_finished_runs_alone(self):
        batch_id = self.create()[0].json()['id']
        self.set_status(batch_id, ['Success', 'Running'])
        data = self.client.post(reverse('cancel_sweep', args=[batch_id])).json()
        self.assertEqual(data['cancelled'], 4)
        self.assertEqual(data['status'], 'Running')
        self.assertEqual([run['status'] for run in data['runs']],
                         ['Success', 'Running', 'Cancelled', 'Cancelled', 'Cancelled', 'Cancelled'])
        # When the active run finishes, the sweep reads as Cancelled.
        self.set_status(batch_id, ['Success', 'Success'])
        self.assertEqual(self.detail(batch_id)['status'], 'Cancelled')

    def test_repeated_cancel_is_harmless(self):
        batch_id = self.create()[0].json()['id']
        first = self.client.post(reverse('cancel_sweep', args=[batch_id])).json()
        second = self.client.post(reverse('cancel_sweep', args=[batch_id])).json()
        self.assertEqual(second['cancelled'], 0)
        self.assertEqual(first['counts'], second['counts'])
        self.assertEqual(second['status'], 'Cancelled')

    def test_cancelled_run_is_never_submitted_whichever_happens_first(self):
        batch_id = self.create()[0].json()['id']
        runs = list(SparkExperiment.objects.filter(batch_id=batch_id).order_by('sweep_index'))
        process = Mock(returncode=1)
        process.stdout.readline.return_value = ''
        with patch('experiments.tasks.SHARED_DIR', self.media_root), \
                patch('experiments.tasks.subprocess.Popen', return_value=process) as popen:
            # The worker claims run 0 first, then the user cancels.
            def cancel_mid_run(*args, **kwargs):
                self.client.post(reverse('cancel_sweep', args=[batch_id]))
                return process
            popen.side_effect = cancel_mid_run
            run_db_script(runs[0].id)
            popen.side_effect = None
            # Tasks for the cancelled runs arrive afterwards.
            for run in runs[1:]:
                run_db_script(run.id)
        self.assertEqual(popen.call_count, 1)
        statuses = list(SparkExperiment.objects.filter(batch_id=batch_id)
                        .order_by('sweep_index').values_list('status', flat=True))
        self.assertEqual(statuses, ['Failed'] + ['Cancelled'] * 5)
        self.assertEqual(self.detail(batch_id)['status'], 'Cancelled')

    def test_rerunning_one_cancelled_run_is_an_ordinary_experiment(self):
        batch_id = self.create()[0].json()['id']
        self.client.post(reverse('cancel_sweep', args=[batch_id]))
        run = SparkExperiment.objects.filter(batch_id=batch_id).first()
        with patch('experiments.views.run_db_script.delay'):
            response = self.client.post(reverse('run_experiment', args=[run.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.detail(batch_id)['status'], 'Queued')

    # Deletion -------------------------------------------------------------

    def test_delete_is_refused_while_runs_are_active(self):
        batch_id = self.create()[0].json()['id']
        response = self.client.delete(reverse('sweep_detail', args=[batch_id]))
        self.assertEqual(response.status_code, 409)
        self.client.post(reverse('cancel_sweep', args=[batch_id]))
        self.set_status(batch_id, ['Running'])
        self.assertEqual(self.client.delete(reverse('sweep_detail', args=[batch_id])).status_code, 409)
        self.assertTrue(SweepBatch.objects.filter(id=batch_id).exists())

    def test_delete_removes_runs_and_their_files(self):
        batch_id = self.create()[0].json()['id']
        self.client.post(reverse('cancel_sweep', args=[batch_id]))
        run = SparkExperiment.objects.filter(batch_id=batch_id).first()
        run.output.save(f'{run.id}.txt', ContentFile(b'log'))
        output_path = Path(run.output.path)
        self.assertTrue(output_path.exists())
        response = self.client.delete(reverse('sweep_detail', args=[batch_id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SweepBatch.objects.filter(id=batch_id).exists())
        self.assertFalse(SparkExperiment.objects.filter(batch_id=batch_id).exists())
        self.assertFalse(output_path.exists())
        self.assertEqual(self.client.get(reverse('sweep_detail', args=[batch_id])).status_code, 404)
