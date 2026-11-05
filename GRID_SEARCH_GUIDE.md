# Hyperparameter Grid Search & Benchmarking Guide

The `grid_search.sh` script automates hyperparameter exploration, experiment execution, result gathering, and benchmark comparison for any algorithm integrated into PICARD.

It natively reads and validates against the **PICARD Algorithm Specification Manifest** format (`spark-classification-v1`, e.g. `codrift.json` and `supervisedmlrf.json`), ensuring all candidate parameters conform to their defined data types, discrete choices, and numerical bounds before execution.

---

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start Examples](#quick-start-examples)
- [Execution Modes](#execution-modes)
  - [1. PICARD API Mode](#1-picard-api-mode)
  - [2. Direct Spark / CLI Mode](#2-direct-spark--cli-mode)
  - [3. Docker Mode](#3-docker-mode)
  - [4. Dry-Run Mode](#4-dry-run-mode)
- [Algorithm Manifest & Grid Specification](#algorithm-manifest--grid-specification)
  - [Algorithm Manifest Schema](#algorithm-manifest-schema)
  - [Grid Search Configuration Format](#grid-search-configuration-format)
  - [CLI Parameter Overrides](#cli-parameter-overrides)
- [Benchmarking Results & Reports](#benchmarking-results--reports)
  - [Output Directory Structure](#output-directory-structure)
  - [Metrics Extraction](#metrics-extraction)
  - [Generated Reports (CSV, JSON, Markdown)](#generated-reports-csv-json-markdown)
- [CLI Reference](#cli-reference)

---

## Features

- **Manifest-Aware Validation**: Validates candidate hyperparameters against the algorithm specification manifest:
  - Integer / Number checks with inclusive and exclusive bounds (`min`, `max`, `exclusiveMin`, `exclusiveMax`).
  - Categorical parameter validation (`choice` parameters such as `impurity` = `gini`, `entropy`).
  - Strict parameter ordering preserving the exact command-line protocol expected by the driver script / JAR.
- **Flexible Grid Specification**:
  - Load candidate parameter arrays from a JSON grid configuration file.
  - Override or supplement parameters directly on the CLI via `-p / --param name=v1,v2,...`.
  - Use `--auto` to automatically test all discrete options of `choice` parameters while keeping defaults for others.
  - Omitted parameters automatically fall back to their manifest defaults.
- **Multiple Execution Backends**:
  - **REST API**: Submits runs to a running PICARD backend instance, tracks progress in real-time, handles duplicate queueing conflicts, and downloads result artifacts.
  - **Direct / Spark**: Invokes `spark-submit` directly on the local machine or remote Spark cluster.
  - **Docker**: Executes jobs inside a running container (`docker exec`).
  - **Dry-run**: Validates inputs and previews all planned combinations and arguments without executing jobs.
- **Benchmarking & Result Gathering**:
  - High-precision wall-clock runtime tracking for each experiment.
  - Automatically parses machine learning metrics (e.g., `Accuracy`, `F1-Score`, `Precision`, `Recall`, `Loss`, `Time taken`).
  - Aggregates logs, outputs, and metrics into a timestamped results directory.
  - Generates three report formats: `benchmark_summary.csv`, `benchmark_summary.json`, and `benchmark_summary.md`.
  - Prints a terminal summary table ranking the best-performing configurations.

---

## Running on Windows

You have three native ways to run the grid search utility on a local Windows machine:

### Option 1: Native PowerShell (`grid_search.ps1`)
Run directly in standard Windows PowerShell without needing Git Bash or WSL:
```powershell
.\grid_search.ps1 -Manifest PICARD2\backend\scripts\manifests\codrift.json -Param "numTrees=10,20", "k=1,2" -DryRun
```

### Option 2: Cross-Platform Python CLI (`grid_search.py`)
Run directly with Python in any Windows terminal (PowerShell, CMD, VS Code terminal):
```powershell
python grid_search.py --manifest PICARD2/backend/scripts/manifests/codrift.json -p numTrees=10,20 -p k=1,2 --dry-run
```

### Option 3: Git Bash or WSL (`grid_search.sh`)
Run the Bash script using Git Bash (installed with Git for Windows) or Windows Subsystem for Linux (WSL):
```bash
# In Git Bash:
./grid_search.sh --manifest PICARD2/backend/scripts/manifests/codrift.json -p numTrees=10,20 --dry-run

# From PowerShell via Git Bash:
& "C:\Program Files\Git\bin\bash.exe" ./grid_search.sh --manifest PICARD2/backend/scripts/manifests/codrift.json -p numTrees=10,20 --dry-run
```

---

## Prerequisites

- **Python 3.7+**: Required across all operating systems.
- **PowerShell 5.1+** (for `.ps1`) or **Bash** (Linux, macOS, WSL, or Git Bash for `.sh`).
- **cURL**: Required for `grid_search.sh` in `--mode api` (built into Python for `grid_search.py`).
- **Apache Spark** (`spark-submit`): Required only when running in `--mode direct`.

---

## Quick Start Examples

### 1. Preview Combinations (Dry-Run)

Validate candidate parameters and inspect the exact arguments string that will be passed without running experiments:

```bash
./grid_search.sh \
  --manifest PICARD2/backend/scripts/manifests/codrift.json \
  -p numTrees=10,20,50 \
  -p impurity=gini,entropy \
  -p maxDepth=3,5 \
  --dry-run
```

### 2. Run via PICARD Web Application (API Mode)

Connects to a running PICARD instance (`http://localhost:8000`), logs in, submits experiments, and monitors them until completion:

```bash
./grid_search.sh \
  --manifest PICARD2/backend/scripts/manifests/supervisedmlrf.json \
  --grid examples/grids/supervisedmlrf_grid.json \
  --mode api \
  --url http://localhost:8000 \
  --username myuser \
  --password mypassword \
  --script-name "SupervisedMLRF" \
  --dataset-name "covtype.csv"
```

### 3. Run Directly on Local Spark Cluster

Runs `spark-submit` directly against a local Spark master:

```bash
./grid_search.sh \
  --manifest PICARD2/backend/scripts/manifests/codrift.json \
  -p numTrees=10,20 \
  -p k=1,2 \
  --mode direct \
  --script-file /opt/spark/apps/codrift.jar \
  --main-class edu.fsu.driver.CoDRIFt \
  --dataset-file /data/covtype.csv \
  --spark-master local[2]
```

---

## Execution Modes

### 1. PICARD API Mode (`--mode api`)

In API mode, `grid_search.sh` interacts with the PICARD Django backend:

1. **Authentication**: Authenticates against `/auth/user_login/` and obtains a session cookie and CSRF token from `/auth/session/`.
2. **Asset Resolution**: If `--script-name` or `--dataset-name` is provided, queries the API to resolve the registered UUIDs. If `--manifest` is omitted, the script automatically downloads the algorithm manifest from the script record!
3. **Queueing & Tracking**: Posts each combination to `/experiments/run/<script_id>/` and polls `/experiments/<id>/` until the experiment status transitions to `Success` or `Failed`.
4. **Artifact Download**: On success, downloads the result file from `/experiments/<id>/result/` and stores the live execution output log.
5. **Conflict Handling**: If an identical experiment is already queued or running (HTTP 409), the script automatically detects the active run and monitors it to completion.

### 2. Direct Spark / CLI Mode (`--mode direct`)

Executes `spark-submit` locally or against a remote cluster without requiring the web backend:

- Commands are built adhering to the PICARD classification protocol:
  ```bash
  spark-submit --master <SPARK_MASTER> --deploy-mode client [--class <MAIN_CLASS>] \
    <SCRIPT_FILE> <DATASET_FILE> <OUTPUT_DIR> spark_out <PARAM_1> <PARAM_2> ...
  ```
- Part-files written to `<OUTPUT_DIR>/spark_out/part-*` are automatically concatenated into `result.txt`.

### 3. Docker Mode (`--mode docker`)

Executes `spark-submit` inside a container (e.g. `spark-master` or `celery_worker`):

```bash
./grid_search.sh \
  --manifest PICARD2/backend/scripts/manifests/codrift.json \
  --grid examples/grids/codrift_grid.json \
  --mode docker \
  --docker-container spark-master \
  --script-file /opt/spark/apps/codrift.jar \
  --main-class edu.fsu.driver.CoDRIFt \
  --dataset-file /app/media/files/datasets/data.csv
```

### 4. Dry-Run Mode (`--dry-run`)

Validates all parameters against the manifest and prints a formatted preview table showing:
- Parameter names and tested values.
- Total combination count.
- The exact positional argument string that will be passed.

---

## Algorithm Manifest & Grid Specification

### Algorithm Manifest Schema

PICARD algorithms define their parameter interface in a JSON manifest (e.g. `codrift.json`, `supervisedmlrf.json`):

```json
{
  "protocol": "spark-classification-v1",
  "input_description": "CSV with numeric features and class label in the last column.",
  "parameters": [
    {
      "name": "numClasses",
      "label": "Number of classes",
      "type": "integer",
      "default": 2,
      "min": 2,
      "max": 2147483647
    },
    {
      "name": "numTrees",
      "label": "Number of trees",
      "type": "integer",
      "default": 10,
      "min": 1,
      "max": 2147483647
    },
    {
      "name": "impurity",
      "label": "Impurity measure",
      "type": "choice",
      "default": "gini",
      "choices": ["gini", "entropy"]
    },
    {
      "name": "percentLabeled",
      "label": "Training data (%)",
      "type": "number",
      "default": 70,
      "exclusiveMin": 0,
      "max": 100
    }
  ]
}
```

### Grid Search Configuration Format

A grid configuration file specifies arrays of candidate values to test. Any parameter omitted from the grid automatically takes its `default` value from the algorithm manifest:

```json
{
  "description": "Grid search configuration for Random Forest classification",
  "parameters": {
    "numTrees": [10, 25, 50],
    "impurity": ["gini", "entropy"],
    "maxDepth": [3, 5, 8]
  }
}
```

Example template files are available in `examples/grids/`:
- `examples/grids/codrift_grid.json`
- `examples/grids/supervisedmlrf_grid.json`
- `examples/grids/sample_custom_grid.json`

### CLI Parameter Overrides

You can pass or override candidate values on the command line using `-p` / `--param`:

```bash
-p numTrees=10,20,50 -p impurity=gini,entropy -p maxDepth=3,5
```

---

## Benchmarking Results & Reports

### Output Directory Structure

Each grid search run produces a timestamped output directory (default: `./benchmark_results_<YYYYMMDD_HHMMSS>`):

```text
benchmark_results_20261105_123000/
├── algorithm_manifest.json     # Saved copy of the manifest used
├── grid_spec.json              # Saved copy of the grid specification
├── .plan.json                  # Complete execution plan
├── benchmark_summary.csv       # Summary table for spreadsheet / Pandas analysis
├── benchmark_summary.json      # Structured report with metadata and all metrics
├── benchmark_summary.md        # Formatted Markdown report with rankings
└── runs/
    ├── run_001/
    │   ├── params.json         # Exact parameters for run 1
    │   ├── output.log          # Full terminal / execution log
    │   └── result.txt          # Result artifact / model output
    ├── run_002/
    │   ├── params.json
    │   ├── output.log
    │   └── result.txt
    └── ...
```

### Metrics Extraction

The benchmarking engine automatically extracts metrics from stdout and result files:
- `accuracy`
- `f1` / `f1-score` / `f-measure`
- `precision`
- `recall`
- `loss`
- `error_rate`
- `auc`
- `duration_sec` / `time_taken_s`
- Custom key-value pairs formatted as `Key: Value` or `Key = Value`.

### Generated Reports (CSV, JSON, Markdown)

#### 1. Markdown Summary (`benchmark_summary.md`)
Contains high-level run statistics, identifies the best configuration, and tabulates ranked results:

| Rank | Run ID | Status | Duration | numTrees | impurity | maxDepth | accuracy | f1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | run_002 | Success | 12.10s | 20 | gini | 5 | 0.9015 | 0.899 |
| 2 | run_001 | Success | 14.52s | 10 | gini | 5 | 0.8842 | 0.8828 |
| 3 | run_003 | Failed | 2.15s | 50 | entropy | 10 | - | - |

#### 2. CSV Summary (`benchmark_summary.csv`)
Comma-separated table containing all hyperparameter columns, durations, statuses, metrics, and artifact paths for easy import into Python/Pandas, R, or Excel.

#### 3. Terminal Summary
A colorized summary table is printed to the terminal upon completion, highlighting the best hyperparameter set.

---

## CLI Reference

```text
Usage: ./grid_search.sh [OPTIONS]

Required (One of the following):
  -m, --manifest <file>        Path to algorithm manifest JSON file (e.g. codrift.json).
  -g, --grid <file>            Path to hyperparameter grid JSON file defining candidate arrays.

Hyperparameter Options:
  -p, --param <name=v1,v2..>   Specify or override candidate values on CLI (repeatable).
  -a, --auto                   Auto-expand all 'choice' parameters; use defaults for others.
  --dry-run                    Validate inputs and preview combinations without executing.

Execution Backend:
  --mode <api|direct|docker>   Backend mode (default: 'api' if URL/script given, else 'direct').

PICARD API Mode:
  -u, --url <url>              PICARD backend URL (default: http://localhost:8000).
  --username <user>            PICARD login username (or env: PICARD_USER).
  --password <pass>            PICARD login password (or env: PICARD_PASSWORD).
  -s, --script-id <uuid>       UUID of Script/Algorithm registered in PICARD.
  --script-name <name>         Display name of Script/Algorithm (auto-resolves UUID).
  -d, --dataset-id <uuid>      UUID of CSV Dataset registered in PICARD.
  --dataset-name <name>        Display name of CSV Dataset (auto-resolves UUID).
  --poll-interval <sec>        Seconds between status polls (default: 3).
  --timeout <sec>              Maximum seconds to wait per experiment (default: 3600).

Direct / Docker Spark Mode:
  --script-file <path>         Path to algorithm file (.py or .jar).
  --dataset-file <path>        Path to dataset CSV file.
  --main-class <class>         Main driver class for JAR execution.
  --spark-master <url>         Spark master URL (default: spark://spark-master:7077).
  --docker-container <name>    Docker container name for 'docker' mode (default: spark-master).
  --cmd-template <template>    Custom command template ({script}, {dataset}, {result_dir}, {result_name}, {args}).

Benchmarking & Reporting:
  -o, --output-dir <dir>       Directory for output logs and reports.
  --metric <name>              Primary metric for ranking (default: accuracy).
  -v, --verbose                Enable verbose debug logging.
  -h, --help                   Display help message and exit.
```
