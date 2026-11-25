import json
from pathlib import Path
import shlex

from django.test import SimpleTestCase

from .sweep_generation import SweepDefinitionError, batch_status, iter_runs, plan_sweep


MANIFESTS = Path(__file__).resolve().parents[1] / 'scripts' / 'manifests'
MLRF = json.loads((MANIFESTS / 'supervisedmlrf.json').read_text())


def plan(definition, limit=100, manifest=MLRF):
    return plan_sweep(manifest, definition, limit)


def values(result, name):
    return next(axis['values'] for axis in result['axes'] if axis['name'] == name)


class SweepGenerationTests(SimpleTestCase):
    def test_defaults_fill_omitted_parameters(self):
        result = plan({})
        self.assertEqual(result['count'], 1)
        runs = list(iter_runs(MLRF, result))
        self.assertEqual(runs, [(0, {
            'numClasses': '2', 'numTrees': '10', 'impurity': 'gini',
            'maxDepth': '5', 'maxBins': '32', 'percentLabeled': '70',
        }, '2 10 gini 5 32 70')])

    def test_fixed_list_and_range_combine_in_manifest_order(self):
        result = plan({'impurity': ['gini', 'entropy'], 'numTrees': {'start': 10, 'stop': 30, 'step': 10}, 'maxDepth': 4})
        self.assertEqual(result['count'], 6)
        runs = list(iter_runs(MLRF, result))
        self.assertEqual([index for index, _, _ in runs], list(range(6)))
        # numTrees precedes impurity in the manifest, so impurity changes fastest.
        self.assertEqual([(p['numTrees'], p['impurity']) for _, p, _ in runs], [
            ('10', 'gini'), ('10', 'entropy'), ('20', 'gini'),
            ('20', 'entropy'), ('30', 'gini'), ('30', 'entropy'),
        ])
        self.assertEqual(runs[0][2], '2 10 gini 4 32 70')
        varied = {axis['name']: axis['varied'] for axis in result['axes']}
        self.assertTrue(varied['numTrees'] and varied['impurity'])
        self.assertFalse(varied['maxDepth'])

    def test_grid_search_tool_format_is_accepted(self):
        result = plan({'parameters': {'numTrees': [10, 25, 50], 'impurity': ['gini', 'entropy']}})
        self.assertEqual(result['count'], 6)

    def test_values_are_deduplicated_after_normalization(self):
        result = plan({'impurity': ['GINI', 'gini', 'Entropy'], 'percentLabeled': [70, '70', 70.0, '70.5']})
        self.assertEqual(values(result, 'impurity'), ['gini', 'entropy'])
        self.assertEqual(values(result, 'percentLabeled'), ['70', '70.5'])
        self.assertEqual(result['count'], 4)

    def test_decimal_ranges_include_the_stop_value(self):
        result = plan({'percentLabeled': {'start': 0.1, 'stop': 0.3, 'step': 0.1}})
        self.assertEqual(values(result, 'percentLabeled'), ['0.1', '0.2', '0.3'])
        result = plan({'percentLabeled': {'start': 10, 'stop': 25, 'step': 10}})
        self.assertEqual(values(result, 'percentLabeled'), ['10', '20'])

    def test_invalid_ranges_are_rejected(self):
        for spec in (
            {'start': 10, 'stop': 1, 'step': 1},
            {'start': 1, 'stop': 10, 'step': 0},
            {'start': 1, 'stop': 10, 'step': -1},
            {'start': 1, 'stop': 10},
            {'start': 'a', 'stop': 10, 'step': 1},
            {'start': 1, 'stop': 'inf', 'step': 1},
        ):
            with self.subTest(spec=spec), self.assertRaises(SweepDefinitionError) as caught:
                plan({'numTrees': spec})
            self.assertIn('numTrees', caught.exception.errors)

    def test_ranges_only_apply_to_numeric_parameters(self):
        with self.assertRaises(SweepDefinitionError) as caught:
            plan({'impurity': {'start': 1, 'stop': 2, 'step': 1}})
        self.assertIn('impurity', caught.exception.errors)

    def test_integer_range_with_fractional_step_is_rejected(self):
        with self.assertRaises(SweepDefinitionError) as caught:
            plan({'numTrees': {'start': 1, 'stop': 2, 'step': 0.5}})
        self.assertIn('integer', caught.exception.errors['numTrees'])

    def test_manifest_bounds_and_choices_are_enforced(self):
        for definition in ({'maxDepth': [5, 31]}, {'impurity': ['gini', 'variance']}, {'percentLabeled': 100}):
            with self.subTest(definition=definition), self.assertRaises(SweepDefinitionError):
                plan(definition)

    def test_unknown_parameters_and_bad_value_types_are_reported(self):
        with self.assertRaises(SweepDefinitionError) as caught:
            plan({'numTress': [1, 2], 'maxDepth': [], 'impurity': True})
        self.assertEqual(set(caught.exception.errors), {'numTress', 'maxDepth', 'impurity'})

    def test_missing_default_is_an_error(self):
        manifest = {'protocol': 'spark-classification-v1', 'parameters': [{'name': 'title', 'type': 'string'}]}
        with self.assertRaises(SweepDefinitionError):
            plan({}, manifest=manifest)
        self.assertEqual(plan({'title': ['a b', "it's"]}, manifest=manifest)['count'], 2)
        runs = list(iter_runs(manifest, plan({'title': ['a b', "it's"]}, manifest=manifest)))
        self.assertEqual([shlex.split(args) for _, _, args in runs], [['a b'], ["it's"]])

    def test_limit_is_checked_before_generating(self):
        with self.assertRaises(SweepDefinitionError) as caught:
            plan({'numTrees': {'start': 1, 'stop': 10**12, 'step': 1}})
        self.assertIn('limit', caught.exception.errors['numTrees'])
        with self.assertRaises(SweepDefinitionError) as caught:
            plan({'numTrees': list(range(1, 11)), 'maxBins': list(range(2, 13))}, limit=100)
        self.assertIn('110 runs', str(caught.exception))
        self.assertEqual(plan({'numTrees': list(range(1, 11)), 'maxBins': list(range(2, 12))})['count'], 100)

    def test_algorithm_without_manifest_is_rejected(self):
        with self.assertRaises(SweepDefinitionError):
            plan_sweep(None, {}, 100)
        with self.assertRaises(SweepDefinitionError):
            plan(['not', 'an', 'object'])


class BatchStatusTests(SimpleTestCase):
    def test_precedence(self):
        cases = [
            ({'Running': 1, 'Queued': 3, 'Cancelled': 2}, True, 'Running'),
            ({'Queued': 1, 'Success': 2}, False, 'Queued'),
            ({'Pending': 1, 'Success': 2}, False, 'Queued'),
            ({'Cancelled': 2, 'Success': 1}, True, 'Cancelled'),
            ({'Success': 3}, True, 'Success'),
            ({'Success': 3}, False, 'Success'),
            ({'Success': 2, 'Failed': 1}, False, 'Completed with failures'),
            ({}, False, 'Completed with failures'),
        ]
        for counts, cancel_requested, expected in cases:
            with self.subTest(counts=counts, cancel_requested=cancel_requested):
                self.assertEqual(batch_status(counts, cancel_requested), expected)
