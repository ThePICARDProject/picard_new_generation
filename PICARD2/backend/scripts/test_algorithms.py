"""Check manifest and argument handling using only the Python standard library."""

import copy
from io import BytesIO
import json
from pathlib import Path
import shlex
from types import SimpleNamespace
import unittest

from scripts.algorithms import (
    get_algorithm_metadata, read_algorithm_manifest,
    validate_algorithm_arguments, validate_algorithm_config,
)


EXAMPLES = Path(__file__).resolve().parents[1] / 'scripts' / 'manifests'


class AlgorithmManifestTests(unittest.TestCase):
    def setUp(self):
        # This deliberately uses parameters unrelated to either bundled JAR.
        self.config = {
            'protocol': 'spark-classification-v1',
            'parameters': [
                {'name': 'trees', 'type': 'integer', 'min': 1, 'max': 10, 'default': 2},
                {'name': 'fraction', 'type': 'number', 'exclusiveMin': 0, 'exclusiveMax': 1, 'default': 0.5},
                {'name': 'mode', 'type': 'choice', 'choices': ['fast', 'accurate'], 'default': 'fast'},
                {'name': 'title', 'type': 'string', 'default': "A user's model"},
            ],
        }
        self.script = SimpleNamespace(name='An entirely new classifier', algorithm_config=self.config)

    def test_examples_supply_the_expected_parameter_values(self):
        for name, expected in [('codrift', '2 10 gini 5 32 70 1'), ('supervisedmlrf', '2 10 gini 5 32 70')]:
            with self.subTest(name=name):
                with (EXAMPLES / f'{name}.json').open('rb') as upload:
                    config = read_algorithm_manifest(upload)
                script = SimpleNamespace(algorithm_config=config)
                self.assertEqual(get_algorithm_metadata(script)['recommended_args'], expected)
                self.assertEqual(validate_algorithm_arguments(script, expected), (expected, ''))

    def test_new_algorithm_and_text_arguments_round_trip_without_name_detection(self):
        validate_algorithm_config(self.config)
        values = ['3', '0.25', 'ACCURATE', "A user's model; $(echo example)"]
        args, error = validate_algorithm_arguments(self.script, values)
        self.assertEqual(error, '')
        self.assertEqual(shlex.split(args), ['3', '0.25', 'accurate', values[-1]])
        self.assertEqual(validate_algorithm_arguments(self.script, args), (args, ''))

    def test_invalid_values_are_rejected_before_execution(self):
        for index, bad in [(0, '0'), (0, '11'), (0, '1.5'), (1, '0'), (1, '1'),
                           (1, 'nan'), (1, 'inf'), (2, 'unknown'), (3, ''), (3, '\0')]:
            with self.subTest(index=index, value=bad):
                values = ['3', '0.25', 'fast', 'model']
                values[index] = bad
                self.assertTrue(validate_algorithm_arguments(self.script, values)[1])
        for args in ['', [], ['3'], {'trees': 3}, [3, '0.25', 'fast', 'model']]:
            self.assertTrue(validate_algorithm_arguments(self.script, args)[1])

    def test_bad_manifests_fail_at_upload(self):
        mutations = [
            {'protocol': 'unknown'}, {'parameters': None}, {'unexpected': True},
            {'parameters': [self.config['parameters'][0]] * 2},
            {'parameters': [{'name': 'bad name', 'type': 'integer'}]},
            {'parameters': [{'name': 'flag', 'type': []}]},
            {'parameters': [{'name': 'flag', 'type': 'choice', 'choices': []}]},
            {'parameters': [{'name': 'flag', 'type': 'choice', 'choices': ['yes', 'YES']}]},
            {'parameters': [{'name': 'flag', 'type': 'string', 'min': 0}]},
            {'parameters': [{'name': 'x', 'type': 'number', 'min': 2, 'max': 1}]},
            {'parameters': [{'name': 'x', 'type': 'number', 'exclusiveMin': 1, 'max': 1}]},
            {'parameters': [{'name': 'x', 'type': 'number', 'max': float('inf')}]},
            {'parameters': [{'name': 'x', 'type': 'integer', 'min': 1, 'default': 0}]},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_algorithm_config({**copy.deepcopy(self.config), **mutation})
        for content in [b'{', b'\xff', b'null', b'[]', b'x' * 65537]:
            with self.subTest(content=content[:10]), self.assertRaises(ValueError):
                read_algorithm_manifest(BytesIO(content))
        self.assertEqual(read_algorithm_manifest(BytesIO(json.dumps(self.config).encode())), self.config)

    def test_legacy_uploads_keep_quoted_arguments_and_check_bad_quotes(self):
        script = SimpleNamespace(name='CoDRIFT name alone grants no settings', algorithm_config=None)
        self.assertIsNone(get_algorithm_metadata(script)['algorithm_config'])
        args, error = validate_algorithm_arguments(script, '"two words" 3')
        self.assertEqual(error, '')
        self.assertEqual(shlex.split(args), ['two words', '3'])
        self.assertIn('unmatched quote', validate_algorithm_arguments(script, '"unfinished')[1])

    def test_empty_parameters_and_missing_defaults_are_supported(self):
        config = {'protocol': 'spark-classification-v1', 'parameters': []}
        validate_algorithm_config(config)
        script = SimpleNamespace(algorithm_config=config)
        self.assertEqual(validate_algorithm_arguments(script, []), ('', ''))
        config['parameters'] = [{'name': 'title', 'type': 'string'}]
        validate_algorithm_config(config)
        self.assertEqual(get_algorithm_metadata(script)['recommended_args'], '')
        self.assertTrue(validate_algorithm_arguments(script, '')[1])
