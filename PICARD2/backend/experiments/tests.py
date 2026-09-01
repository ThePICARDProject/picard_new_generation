import shutil
import tempfile
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
        with self.experiment.output.open('r') as output_file:
            output = output_file.read()
        self.assertIn('new attempt output', output)
        self.assertNotIn('previous failure', output)
