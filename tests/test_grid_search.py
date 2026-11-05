"""Test suite for PICARD grid search logic and algorithm manifest integration."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Paths
REPO_ROOT = Path(__file__).resolve().parents[1]
GRID_SCRIPT = REPO_ROOT / "grid_search.sh"
CODRIFT_MANIFEST = REPO_ROOT / "PICARD2" / "backend" / "scripts" / "manifests" / "codrift.json"
SUPERVISED_MANIFEST = REPO_ROOT / "PICARD2" / "backend" / "scripts" / "manifests" / "supervisedmlrf.json"


class GridSearchEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Extract embedded python engine from grid_search.sh
        with open(GRID_SCRIPT, 'r', encoding='utf-8') as f:
            script_text = f.read()

        delimiter = "PYTHON_ENGINE_SCRIPT"
        first_pos = script_text.find(delimiter)
        second_pos = script_text.find(delimiter, first_pos + len(delimiter))

        line_after_first = script_text.find('\n', first_pos) + 1
        line_before_second = script_text.rfind('\n', first_pos, second_pos)

        py_code = script_text[line_after_first:line_before_second]

        cls.engine_namespace = {}
        exec(compile(py_code, 'grid_engine', 'exec'), cls.engine_namespace)

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.temp_dir)

    def test_codrift_manifest_parameter_types_and_defaults(self):
        with open(CODRIFT_MANIFEST, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        normalize = self.engine_namespace['normalize_param']
        param_dict = {p['name']: p for p in manifest['parameters']}

        # Verify defaults normalize correctly
        for p in manifest['parameters']:
            normalized = normalize(p, p['default'])
            self.assertEqual(normalized, str(p['default']))

        # Test bounds
        with self.assertRaises(ValueError):
            normalize(param_dict['numTrees'], 0)  # min is 1
        with self.assertRaises(ValueError):
            normalize(param_dict['maxDepth'], 35)  # max is 30
        with self.assertRaises(ValueError):
            normalize(param_dict['impurity'], 'invalid_choice')

    def test_supervisedmlrf_grid_cartesian_product(self):
        with open(SUPERVISED_MANIFEST, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        # Set up args mock
        class Args:
            manifest = str(SUPERVISED_MANIFEST)
            manifest_json = None
            grid = None
            param = ['numTrees=10,20', 'impurity=gini,entropy', 'maxDepth=5,10']
            auto = False

        # Capture output from cmd_generate
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            self.engine_namespace['cmd_generate'](Args())
        output = json.loads(f.getvalue())

        # 2 trees * 2 impurity * 2 maxDepth = 8 combinations
        self.assertEqual(output['total_combinations'], 8)
        self.assertEqual(len(output['runs']), 8)

        first_run = output['runs'][0]
        # Parameters: numClasses, numTrees, impurity, maxDepth, maxBins, percentLabeled
        self.assertEqual(first_run['params']['numClasses'], '2')
        self.assertEqual(first_run['params']['numTrees'], '10')
        self.assertEqual(first_run['params']['impurity'], 'gini')
        self.assertEqual(first_run['params']['maxDepth'], '5')
        self.assertEqual(first_run['args_string'], '2 10 gini 5 32 70')

    def test_auto_choice_expansion(self):
        class Args:
            manifest = str(CODRIFT_MANIFEST)
            manifest_json = None
            grid = None
            param = None
            auto = True  # auto expand choices (gini, entropy)

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            self.engine_namespace['cmd_generate'](Args())
        output = json.loads(f.getvalue())

        # CoDRIFT has 1 choice param with 2 options, remaining params use defaults -> 2 runs
        self.assertEqual(output['total_combinations'], 2)
        impurities = [r['params']['impurity'] for r in output['runs']]
        self.assertEqual(sorted(impurities), ['entropy', 'gini'])

    def test_metric_parsing_and_report_generation(self):
        parse_metrics = self.engine_namespace['parse_metrics']
        log_sample = """
        Driver CoDRIFt running on Spark.
        Iteration 1: completed
        Accuracy = 0.9125
        Precision = 0.9010
        Recall: 0.9240
        F1-score: 0.9124
        Time taken: 15.24s
        """
        metrics = parse_metrics(log_sample, "Additional notes")
        self.assertEqual(metrics['accuracy'], 0.9125)
        self.assertEqual(metrics['precision'], 0.901)
        self.assertEqual(metrics['recall'], 0.924)
        self.assertEqual(metrics['f1'], 0.9124)

        # Test report generation
        runs_state = [
            {
                "run_id": "run_001",
                "status": "Success",
                "duration_sec": 15.24,
                "params": {"numTrees": "10", "impurity": "gini"},
                "args_string": "2 10 gini 5 32 70 1",
                "output_log": "",
                "result_file": "",
                "metrics": metrics
            },
            {
                "run_id": "run_002",
                "status": "Success",
                "duration_sec": 12.10,
                "params": {"numTrees": "20", "impurity": "entropy"},
                "args_string": "2 20 entropy 5 32 70 1",
                "output_log": "",
                "result_file": "",
                "metrics": {"accuracy": 0.9350, "f1": 0.9320}
            }
        ]

        state_file = os.path.join(self.temp_dir, 'state.json')
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(runs_state, f)

        class ReportArgs:
            results_json = state_file
            output_dir = self.temp_dir
            manifest = str(CODRIFT_MANIFEST)
            primary_metric = 'accuracy'

        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            self.engine_namespace['cmd_report'](ReportArgs())

        # Verify reports generated
        csv_path = os.path.join(self.temp_dir, 'benchmark_summary.csv')
        json_path = os.path.join(self.temp_dir, 'benchmark_summary.json')
        md_path = os.path.join(self.temp_dir, 'benchmark_summary.md')

        self.assertTrue(os.path.isfile(csv_path))
        self.assertTrue(os.path.isfile(json_path))
        self.assertTrue(os.path.isfile(md_path))

        with open(json_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        self.assertEqual(summary['total_runs'], 2)
        self.assertEqual(summary['successful_runs'], 2)
        self.assertEqual(summary['best_run']['run_id'], 'run_002')
        self.assertEqual(summary['best_run']['metrics']['accuracy'], 0.9350)

    def test_bounds_and_numeric_validation(self):
        normalize = self.engine_namespace['normalize_param']
        param = {'name': 'rate', 'type': 'number', 'exclusiveMin': 0, 'exclusiveMax': 1, 'label': 'Rate'}

        # Valid float
        self.assertEqual(normalize(param, 0.5), '0.5')
        self.assertEqual(normalize(param, '0.01'), '0.01')

        # Invalid bounds
        with self.assertRaises(ValueError):
            normalize(param, 0.0)  # must be > exclusiveMin
        with self.assertRaises(ValueError):
            normalize(param, 1.0)  # must be < exclusiveMax
        with self.assertRaises(ValueError):
            normalize(param, -0.5)
        with self.assertRaises(ValueError):
            normalize(param, 'not-a-number')

    def test_generic_metrics_and_edge_cases(self):
        parse_metrics = self.engine_namespace['parse_metrics']
        raw_text = """
        [System: Model Evaluation Complete]
        loss: 0.0451
        error_rate = 0.032
        ROC-AUC: 0.987
        F-measure: 0.951
        custom_metric: 42.5
        """
        metrics = parse_metrics(raw_text, "")
        self.assertEqual(metrics['loss'], 0.0451)
        self.assertEqual(metrics['error_rate'], 0.032)
        self.assertEqual(metrics['auc'], 0.987)
        self.assertEqual(metrics['f1'], 0.951)
        self.assertEqual(metrics['custom_metric'], 42.5)

    def test_missing_required_param_in_grid_without_default(self):
        class BadArgs:
            manifest = None
            manifest_json = json.dumps({
                "protocol": "spark-classification-v1",
                "parameters": [
                    {"name": "requiredNoDefault", "type": "integer"}
                ]
            })
            grid = None
            param = None
            auto = False

        with self.assertRaises(ValueError):
            self.engine_namespace['cmd_generate'](BadArgs())


if __name__ == '__main__':
    unittest.main()
