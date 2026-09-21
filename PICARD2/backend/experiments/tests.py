from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from experiments.tasks import run_db_script


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
                str(Path(directory) / 'results_demo.txt'), '2', '10', 'gini', '5', '32', '70', '1', 'two words',
            ])
            self.assertEqual(experiment.status, 'Success')
