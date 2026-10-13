import json
import shlex
import shutil
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock, patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, SimpleTestCase, override_settings
from django.urls import reverse
from kombu.exceptions import OperationalError
from rest_framework.test import APIClient

from datasets.models import CSVDataset
from scripts.models import Script

from .models import SparkExperiment
from .tasks import run_db_script


EXAMPLES = Path(__file__).resolve().parents[1] / 'scripts' / 'manifests'


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
            algorithm_config=json.loads((EXAMPLES / 'codrift.json').read_text()),
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
        self.assertIn('requires 7 arguments', response.json()['error'])

    def test_codrift_recommendation_is_exposed_and_accepted(self):
        codrift = Script.objects.create(
            user=self.user,
            name='CoDRIFT',
            file_type=Script.JAR,
            file='files/scripts/codrift.jar',
            main_class='edu.fsu.driver.CoDRIFt',
            algorithm_config=json.loads((EXAMPLES / 'codrift.json').read_text()),
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

    @patch('experiments.views.run_db_script.delay')
    def test_new_classifier_upload_to_queue_without_application_changes(self, delay):
        # Register an unrelated algorithm through the same API the browser uses.
        config = {'protocol': 'spark-classification-v1', 'parameters': [
            {'name': 'title', 'type': 'string', 'default': "A user's model"},
        ]}
        response = self.client.post('/scripts/upload/', {
            'script': SimpleUploadedFile('new_classifier.py', b'print("example")'),
            'algorithm_manifest': SimpleUploadedFile('new_classifier.json', json.dumps(config).encode()),
        }, format='multipart')
        self.assertEqual(response.status_code, 200)
        script_id = response.json()['script_id']
        listed = next(script for script in self.client.get(reverse('list_scripts')).json() if script['id'] == script_id)
        self.assertEqual(listed['algorithm_config'], config)
        response = self.client.post(reverse('create_experiment'), {
            'script_id': script_id, 'dataset_id': str(self.dataset.id), 'args': ["A user's model"],
        }, format='json')
        self.assertEqual(response.status_code, 201)
        experiment = SparkExperiment.objects.get(id=response.json()['experiment_id'])
        self.assertEqual(shlex.split(experiment.args), ["A user's model"])
        response = self.client.post(reverse('run_experiment', args=[experiment.id]))
        self.assertEqual(response.status_code, 200)
        delay.assert_called_once_with(experiment.id)

    @patch('experiments.views.run_db_script.delay')
    def test_saved_arguments_are_validated_before_queueing(self, delay):
        self.script.algorithm_config = json.loads((EXAMPLES / 'supervisedmlrf.json').read_text())
        self.script.save()
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 400)
        delay.assert_not_called()
        self.experiment.refresh_from_db()
        self.assertEqual(self.experiment.status, 'Failed')

    @patch('experiments.tasks.subprocess.Popen')
    def test_classifier_results_are_imported_in_filename_order(self, popen):
        self.script.algorithm_config = {'protocol': 'spark-classification-v1', 'parameters': []}
        self.script.save()

        def write_report(command, **kwargs):
            # Act like an algorithm honoring the directory/name contract.
            self.assertEqual(command[4], self.dataset.get_absolute_file_path())
            directory = Path(command[5]) / command[6]
            directory.mkdir()
            (directory / 'part-00001').write_text('second\n')
            (directory / 'part-00000').write_text('first\n')
            (directory / '_SUCCESS').touch()
            process = Mock(returncode=0)
            process.stdout.readline.return_value = ''
            return process

        popen.side_effect = write_report
        with patch('experiments.tasks.SHARED_DIR', self.media_root):
            run_db_script(self.experiment.id)
        self.experiment.refresh_from_db()
        self.assertEqual(self.experiment.status, 'Success')
        with self.experiment.result.open('rb') as result:
            self.assertEqual(result.read(), b'first\nsecond\n')
        self.assertFalse((Path(self.media_root) / f'results_{self.experiment.id}.txt').exists())

    @patch('experiments.tasks.subprocess.Popen')
    def test_classifier_without_a_report_is_failed(self, popen):
        self.script.algorithm_config = {'protocol': 'spark-classification-v1', 'parameters': []}
        self.script.save()
        popen.return_value = Mock(returncode=0)
        popen.return_value.stdout.readline.return_value = ''
        with patch('experiments.tasks.SHARED_DIR', self.media_root):
            run_db_script(self.experiment.id)
        self.experiment.refresh_from_db()
        self.assertEqual(self.experiment.status, 'Failed')
        self.assertFalse(self.experiment.result.name)


class SparkCommandTests(SimpleTestCase):
    def test_main_class_precedes_jar_and_quoted_arguments_are_forwarded(self):
        self.check_command('jar', 'example.Driver', [
            'spark-submit', '--master', 'spark://spark-master:7077',
            '--class', 'example.Driver', '/scripts/job.jar', '/data/input.csv',
        ])

    def test_python_has_no_class_option(self):
        self.check_command('py', '', [
            'spark-submit', '--master', 'spark://spark-master:7077',
            '/scripts/job.py', '/data/input.csv',
        ])

    def check_command(self, file_type, main_class, prefix):
        with TemporaryDirectory() as directory:
            experiment = Mock(id='demo', args='2 10 gini 5 32 70 1 "two words"')
            experiment.script.file_type = file_type
            experiment.script.algorithm_config = None
            experiment.script.main_class = main_class
            experiment.script.get_absolute_file_path.return_value = f'/scripts/job.{file_type}'
            experiment.dataset.get_absolute_file_path.return_value = '/data/input.csv'
            experiment.get_absolute_output_path.return_value = str(Path(directory) / 'output.txt')
            process = Mock(returncode=0)
            process.stdout.readline.return_value = ''
            with patch('experiments.tasks.SparkExperiment.objects') as objects, \
                    patch('experiments.tasks.SHARED_DIR', directory), \
                    patch('experiments.tasks.subprocess.Popen', return_value=process) as popen:
                objects.select_related.return_value.get.return_value = experiment
                run_db_script('demo')
            self.assertEqual(popen.call_args.args[0], prefix + [
                directory, 'results_demo.txt', '2', '10', 'gini', '5', '32', '70', '1', 'two words',
            ])
            self.assertEqual(experiment.status, 'Success')
