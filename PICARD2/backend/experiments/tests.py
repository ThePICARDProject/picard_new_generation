import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from datasets.models import CSVDataset
from scripts.models import Script

from .models import SparkExperiment
from .tasks import run_db_script


class RunExperimentTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root)

        self.user = User.objects.create_user(username='rerun-user')
        self.script = Script.objects.create(
            user=self.user,
            name='algorithm.py',
            file_type=Script.PYTHON,
            file='files/scripts/algorithm.py',
        )
        self.dataset = CSVDataset.objects.create(
            user=self.user,
            name='dataset.csv',
            file='files/datasets/dataset.csv',
        )
        self.experiment = SparkExperiment.objects.create(
            user=self.user,
            script=self.script,
            dataset=self.dataset,
            status='Failed',
        )
        self.experiment.output.save('output.txt', ContentFile('previous failure'), save=False)
        self.experiment.result.save('result.txt', ContentFile('previous result'), save=True)

        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse('run_experiment', args=[self.experiment.id])

    @patch('experiments.views.run_db_script.delay')
    def test_rerun_is_queued_without_discarding_artifacts(self, delay):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.experiment.refresh_from_db()
        self.assertEqual(self.experiment.status, 'Queued')
        self.assertTrue(self.experiment.output.storage.exists(self.experiment.output.name))
        self.assertTrue(self.experiment.result.storage.exists(self.experiment.result.name))
        delay.assert_called_once_with(self.experiment.id)

    @patch(
        'experiments.views.run_db_script.delay',
        side_effect=OperationalError('broker unavailable'),
    )
    def test_broker_failure_returns_json_and_restores_failed_run(self, delay):
        output_name = self.experiment.output.name
        result_name = self.experiment.result.name

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {'error': 'Experiment execution service is unavailable. Please try again shortly.'},
        )
        self.experiment.refresh_from_db()
        self.assertEqual(self.experiment.status, 'Failed')
        self.assertEqual(self.experiment.output.name, output_name)
        self.assertEqual(self.experiment.result.name, result_name)
        self.assertTrue(self.experiment.output.storage.exists(output_name))
        self.assertTrue(self.experiment.result.storage.exists(result_name))

    @patch('experiments.tasks.subprocess.Popen')
    def test_worker_replaces_artifacts_after_accepting_rerun(self, popen):
        old_output_name = self.experiment.output.name
        old_result_name = self.experiment.result.name
        stale_result_directory = (
            Path(self.media_root) / f'results_{self.experiment.id}.txt'
        )
        stale_result_directory.mkdir()
        (stale_result_directory / 'incomplete-result').write_text('stale')
        process = MagicMock()
        process.stdout.readline.side_effect = ['new attempt output\n', '']
        process.returncode = 1
        popen.return_value = process

        with patch('experiments.tasks.SHARED_DIR', self.media_root):
            run_db_script(self.experiment.id)

        self.experiment.refresh_from_db()
        self.assertEqual(self.experiment.status, 'Failed')
        self.assertEqual(self.experiment.output.name, old_output_name)
        self.assertFalse(self.experiment.result.name)
        self.assertFalse(self.experiment.result.storage.exists(old_result_name))
        self.assertFalse(stale_result_directory.exists())
        with self.experiment.output.open('r') as output_file:
            output = output_file.read()
        self.assertIn('new attempt output', output)
        self.assertNotIn('previous failure', output)

    def test_codrift_requires_all_seven_arguments(self):
        codrift = Script.objects.create(
            user=self.user,
            name='codrift_2.12-1.0.jar',
            file_type=Script.JAR,
            file='files/scripts/codrift.jar',
            main_class='edu.fsu.driver.CoDRIFt',
        )

        response = self.client.post(
            reverse('create_experiment'),
            {
                'script_id': str(codrift.id),
                'dataset_id': str(self.dataset.id),
                'args': '',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('requires seven arguments', response.json()['error'])

    def test_codrift_recommendation_is_exposed_and_accepted(self):
        codrift = Script.objects.create(
            user=self.user,
            name='CoDRIFT',
            file_type=Script.JAR,
            file='files/scripts/codrift.jar',
            main_class='edu.fsu.driver.CoDRIFt',
        )

        scripts_response = self.client.get(reverse('list_scripts'))
        script_data = next(
            script for script in scripts_response.json()
            if script['id'] == str(codrift.id)
        )
        self.assertTrue(script_data['arguments_required'])
        self.assertEqual(script_data['recommended_args'], '2 10 gini 5 32 70 1')

        create_response = self.client.post(
            reverse('create_experiment'),
            {
                'script_id': str(codrift.id),
                'dataset_id': str(self.dataset.id),
                'args': '2 10 GINI 5 32 70 1',
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201)
        experiment = SparkExperiment.objects.get(id=create_response.json()['experiment_id'])
        self.assertEqual(experiment.args, '2 10 gini 5 32 70 1')
