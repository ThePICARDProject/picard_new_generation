"""Verify actual argument positions without needing Spark or a database."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from experiments.commands import build_spark_command


EXAMPLES = Path(__file__).resolve().parents[1] / 'scripts' / 'manifests'


class SparkCommandTests(unittest.TestCase):
    def test_both_artifacts_receive_directory_and_name_before_their_parameters(self):
        examples = [
            ('codrift', 'edu.fsu.driver.CoDRIFt', ['2', '10', 'gini', '5', '32', '70', '1']),
            ('supervisedmlrf', 'edu.wvu.rascl.driver.SupervisedMLRF', ['2', '10', 'gini', '5', '32', '70']),
        ]
        for name, main_class, args in examples:
            with self.subTest(name=name):
                script = SimpleNamespace(
                    file_type='jar', main_class=main_class,
                    get_absolute_file_path=lambda: '/uploads/job.jar',
                    algorithm_config=json.loads((EXAMPLES / f'{name}.json').read_text()),
                )
                self.assertEqual(build_spark_command(script, '/data/input.csv', '/shared/result-123', args), [
                    'spark-submit', '--master', 'spark://spark-master:7077', '--class', main_class,
                    '/uploads/job.jar', '/data/input.csv', '/shared', 'result-123', *args,
                ])

    def test_new_python_classifier_preserves_spaces_as_one_argument(self):
        script = SimpleNamespace(
            file_type='py', main_class='', get_absolute_file_path=lambda: '/uploads/job.py',
            algorithm_config={'protocol': 'spark-classification-v1', 'parameters': [
                {'name': 'title', 'type': 'string'},
            ]},
        )
        command = build_spark_command(script, '/data/input file.csv', '/shared/result 123', ['two words'])
        self.assertEqual(command[3:], ['/uploads/job.py', '/data/input file.csv', '/shared', 'result 123', 'two words'])
        with self.assertRaises(ValueError):
            build_spark_command(script, None, '/shared/result', ['two words'])
        with self.assertRaises(ValueError):
            build_spark_command(script, '/data/input.csv', '/shared/result', [])

    def test_unconfigured_scripts_keep_the_complete_output_path(self):
        script = SimpleNamespace(
            file_type='py', main_class='', algorithm_config=None,
            get_absolute_file_path=lambda: '/uploads/job.py',
        )
        command = build_spark_command(script, '/data/input.csv', '/shared/result', '"two words"')
        self.assertEqual(command[3:], ['/uploads/job.py', '/data/input.csv', '/shared/result', 'two words'])
