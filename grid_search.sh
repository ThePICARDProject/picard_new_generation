#!/usr/bin/env bash
# ==============================================================================
# PICARD Algorithm Hyperparameter Grid Search & Benchmarking Utility
# ==============================================================================
# Automates hyperparameter exploration, experiment execution, result gathering,
# and benchmarking comparisons for algorithms conforming to the PICARD
# algorithm specification manifest protocol (spark-classification-v1).
# ==============================================================================

set -eo pipefail

# ------------------------------------------------------------------------------
# Terminal Formatting & Colors
# ------------------------------------------------------------------------------
if [[ -t 1 ]] && [[ "${NO_COLOR:-}" != "1" ]]; then
  BOLD="\033[1m"
  DIM="\033[2m"
  GREEN="\033[0;32m"
  YELLOW="\033[0;33m"
  RED="\033[0;31m"
  BLUE="\033[0;34m"
  CYAN="\033[0;36m"
  MAGENTA="\033[0;35m"
  RESET="\033[0m"
else
  BOLD=""
  DIM=""
  GREEN=""
  YELLOW=""
  RED=""
  BLUE=""
  CYAN=""
  MAGENTA=""
  RESET=""
fi

log_info()    { echo -e "${BLUE}[INFO]${RESET} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${RESET} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
log_error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
log_step()    { echo -e "\n${BOLD}${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }

# ------------------------------------------------------------------------------
# Usage / Help Documentation
# ------------------------------------------------------------------------------
show_help() {
  cat << EOF
${BOLD}PICARD Hyperparameter Grid Search & Benchmarking Tool${RESET}

${BOLD}USAGE:${RESET}
  $0 [OPTIONS]

${BOLD}DESCRIPTION:${RESET}
  Runs a systematic grid search across hyperparameter combinations for any
  given algorithm, automatically validating parameter bounds and types against
  its algorithm specification manifest (e.g. codrift.json, supervisedmlrf.json).
  Gathers outputs, extracts performance metrics (accuracy, f1, precision, recall,
  runtime duration), and generates comprehensive benchmark comparison reports
  (CSV, JSON, Markdown, and formatted terminal table).

${BOLD}SPECIFICATION & GRID OPTIONS:${RESET}
  -m, --manifest <file>        Path to algorithm manifest JSON file (e.g. codrift.json).
                               (If omitted in API mode, manifest is fetched from the server).
  -g, --grid <file>            Path to hyperparameter grid JSON file defining candidate arrays.
  -p, --param <name=v1,v2..>   Specify or override candidate values on CLI (repeatable).
                               Example: -p numTrees=10,20,50 -p impurity=gini,entropy
  -a, --auto                   Auto-expand all 'choice' parameters to their allowed choices;
                               uses manifest defaults for numeric/string parameters.
  --dry-run                    Validate inputs, print the generated grid matrix, and exit
                               without executing any jobs.

${BOLD}EXECUTION MODE OPTIONS:${RESET}
  --mode <api|direct|docker>   Execution mode (default: 'api' if URL/script is given, else 'direct'):
                                 - ${BOLD}api${RESET}:    Submit to PICARD REST API, poll status, download results.
                                 - ${BOLD}direct${RESET}: Execute spark-submit directly on local machine/cluster.
                                 - ${BOLD}docker${RESET}: Execute spark-submit inside a running Docker container.

${BOLD}PICARD API MODE OPTIONS:${RESET}
  -u, --url <url>              PICARD backend URL (default: \${BACKEND_LOCAL_URL:-http://localhost:8000})
  --username <user>            PICARD login username (or env: PICARD_USER)
  --password <pass>            PICARD login password (or env: PICARD_PASSWORD)
  -s, --script-id <uuid>       UUID of Script/Algorithm registered in PICARD.
  --script-name <name>         Display name of Script/Algorithm (auto-resolves UUID & manifest).
  -d, --dataset-id <uuid>      UUID of CSV Dataset registered in PICARD.
  --dataset-name <name>        Display name of CSV Dataset (auto-resolves UUID).
  --poll-interval <sec>        Seconds between experiment status polls (default: 3).
  --timeout <sec>              Maximum seconds to wait per experiment run (default: 3600).

${BOLD}DIRECT / DOCKER MODE OPTIONS:${RESET}
  --script-file <path>         Path to algorithm file (.py or .jar).
  --dataset-file <path>        Path to dataset CSV file.
  --main-class <class>         Main driver class for JAR execution (e.g. edu.fsu.driver.CoDRIFt).
  --spark-master <url>         Spark master URL (default: \${SPARK_MASTER_URL:-spark://spark-master:7077}).
  --docker-container <name>    Docker container name for 'docker' mode (default: spark-master).
  --cmd-template <template>    Custom command template. Placeholders:
                               {script}, {dataset}, {result_dir}, {result_name}, {args}

${BOLD}BENCHMARKING & REPORTING OPTIONS:${RESET}
  -o, --output-dir <dir>       Directory to store logs and reports (default: ./benchmark_results_<timestamp>).
  --metric <name>              Primary metric for ranking (e.g. accuracy, f1, duration; default: accuracy).
  -v, --verbose                Enable verbose debug output.
  -h, --help                   Display this help message and exit.

${BOLD}EXAMPLES:${RESET}
  ${DIM}# 1. Dry-run preview of grid combinations using manifest & CLI overrides:${RESET}
  $0 --manifest PICARD2/backend/scripts/manifests/codrift.json \\
     -p numTrees=10,20,50 -p impurity=gini,entropy --dry-run

  ${DIM}# 2. Run grid search via PICARD API with username/password:${RESET}
  $0 --manifest PICARD2/backend/scripts/manifests/supervisedmlrf.json \\
     --grid examples/grids/supervisedmlrf_grid.json \\
     --mode api --url http://localhost:8000 \\
     --username admin --password secret \\
     --script-name "SupervisedMLRF" --dataset-name "sample.csv"

  ${DIM}# 3. Run grid search directly using local spark-submit:${RESET}
  $0 --manifest PICARD2/backend/scripts/manifests/codrift.json \\
     -p numTrees=10,20 -p k=1,2 \\
     --mode direct \\
     --script-file /opt/spark/apps/codrift.jar \\
     --main-class edu.fsu.driver.CoDRIFt \\
     --dataset-file /data/dataset.csv \\
     --spark-master local[2]

EOF
}

# ------------------------------------------------------------------------------
# Locate Python 3 Interpreter
# ------------------------------------------------------------------------------
PYTHON_BIN=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 7) else 1)" 2>/dev/null; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  log_error "Python 3.7+ is required by grid_search.sh for manifest validation and reporting."
  exit 1
fi

# ------------------------------------------------------------------------------
# High-Resolution Time Helper
# ------------------------------------------------------------------------------
get_timestamp_sec() {
  "$PYTHON_BIN" -c "import time; print(f'{time.time():.4f}')" 2>/dev/null || date +%s
}

format_time() {
  local sec="$1"
  "$PYTHON_BIN" -c "
s = float('$sec')
if s < 60:
    print(f'{s:.2f}s')
else:
    m = int(s // 60)
    print(f'{m}m {s % 60:.1f}s')
" 2>/dev/null || echo "${sec}s"
}

# ------------------------------------------------------------------------------
# Embedded Python Engine
# ------------------------------------------------------------------------------
run_python_engine() {
  "$PYTHON_BIN" - "$@" << 'PYTHON_ENGINE_SCRIPT'
import argparse
import csv
import itertools
import json
import math
import os
import re
import shlex
import sys

def normalize_param(param, value):
    label = param.get('label') or param['name']
    kind = param['type']
    text = str(value).strip()

    if kind in ('integer', 'number'):
        try:
            if kind == 'integer':
                if not re.fullmatch(r'[+-]?[0-9]+', text):
                    raise ValueError
                num = int(text)
            else:
                num = float(text)
                if not math.isfinite(num):
                    raise ValueError
        except (ValueError, OverflowError):
            raise ValueError(f"Parameter '{param['name']}': expected a finite {kind}, got '{value}'")

        if 'min' in param and num < param['min']:
            raise ValueError(f"Parameter '{param['name']}': {num} is less than min ({param['min']})")
        if 'max' in param and num > param['max']:
            raise ValueError(f"Parameter '{param['name']}': {num} is greater than max ({param['max']})")
        if 'exclusiveMin' in param and num <= param['exclusiveMin']:
            raise ValueError(f"Parameter '{param['name']}': {num} must be > exclusiveMin ({param['exclusiveMin']})")
        if 'exclusiveMax' in param and num >= param['exclusiveMax']:
            raise ValueError(f"Parameter '{param['name']}': {num} must be < exclusiveMax ({param['exclusiveMax']})")
        return str(int(num)) if num == int(num) else str(num)

    if kind == 'choice':
        for choice in param.get('choices', []):
            if text.casefold() == choice.casefold():
                return choice
        choices_str = ', '.join(f"'{c}'" for c in param.get('choices', []))
        raise ValueError(f"Parameter '{param['name']}': '{text}' is not one of allowed choices: [{choices_str}]")

    if not text:
        raise ValueError(f"Parameter '{param['name']}': string value cannot be empty")
    return text

def parse_cli_params(cli_params_list):
    res = {}
    for item in cli_params_list or []:
        if '=' not in item:
            raise ValueError(f"Invalid --param format: '{item}'. Expected format is 'paramName=val1,val2,...'")
        name, raw_vals = item.split('=', 1)
        name = name.strip()
        vals = [v.strip() for v in raw_vals.split(',') if v.strip()]
        res[name] = vals
    return res

def cmd_generate(args):
    manifest_data = {}
    if args.manifest:
        with open(args.manifest, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
    elif args.manifest_json:
        manifest_data = json.loads(args.manifest_json)
    else:
        raise ValueError("Either --manifest file or --manifest-json must be provided.")

    grid_data = {}
    if args.grid:
        with open(args.grid, 'r', encoding='utf-8') as f:
            grid_data = json.load(f)
            if "parameters" in grid_data and isinstance(grid_data["parameters"], dict):
                grid_data = grid_data["parameters"]
            elif "grid" in grid_data and isinstance(grid_data["grid"], dict):
                grid_data = grid_data["grid"]

    cli_params = parse_cli_params(args.param)
    grid_data.update(cli_params)

    params = manifest_data.get('parameters', [])
    if not params:
        raise ValueError("Algorithm manifest contains no parameter definitions.")

    param_pools = []
    param_names = []
    for p in params:
        name = p['name']
        param_names.append(name)
        if name in grid_data:
            raw = grid_data[name]
            candidates = raw if isinstance(raw, list) else [raw]
        elif args.auto and p.get('type') == 'choice' and p.get('choices'):
            candidates = p['choices']
        elif 'default' in p and p['default'] is not None:
            candidates = [p['default']]
        else:
            raise ValueError(f"Parameter '{name}' is required by manifest but has no candidates in grid and no default value.")

        normalized = [normalize_param(p, c) for c in candidates]
        param_pools.append(normalized)

    runs = []
    for idx, combo in enumerate(itertools.product(*param_pools), 1):
        combo_dict = dict(zip(param_names, combo))
        args_list = list(combo)
        runs.append({
            "run_id": f"run_{idx:03d}",
            "run_index": idx,
            "params": combo_dict,
            "args_list": args_list,
            "args_string": shlex.join(args_list)
        })

    output_data = {
        "protocol": manifest_data.get("protocol", "spark-classification-v1"),
        "total_combinations": len(runs),
        "parameter_names": param_names,
        "runs": runs
    }
    print(json.dumps(output_data, indent=2))

def parse_metrics(output_text, result_text):
    metrics = {}
    combined = (output_text or "") + "\n" + (result_text or "")
    patterns = {
        "accuracy": [r'(?i)\baccuracy\b\s*[:=]\s*([0-9.]+)', r'(?i)\baccuracy\b\s+([0-9.]+)%'],
        "precision": [r'(?i)\bprecision\b\s*[:=]\s*([0-9.]+)'],
        "recall": [r'(?i)\brecall\b\s*[:=]\s*([0-9.]+)'],
        "f1": [r'(?i)\bf1(?:-score)?\b\s*[:=]\s*([0-9.]+)', r'(?i)\bf-measure\b\s*[:=]\s*([0-9.]+)'],
        "loss": [r'(?i)\bloss\b\s*[:=]\s*([0-9.]+)'],
        "error_rate": [r'(?i)\berror(?:\s+rate)?\b\s*[:=]\s*([0-9.]+)'],
        "auc": [r'(?i)\b(?:roc-)?auc\b\s*[:=]\s*([0-9.]+)'],
        "time_taken_s": [r'(?i)(?:time\s+taken|execution\s+time|duration)\s*[:=]\s*([0-9.]+)\s*s(?:ec|econds)?\b']
    }
    for metric_name, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, combined)
            if m:
                val = m.group(1).strip()
                try:
                    num = float(val)
                    metrics[metric_name] = round(num, 6)
                except ValueError:
                    metrics[metric_name] = val
                break

    for line in combined.splitlines():
        line = line.strip()
        m = re.match(r'^([A-Za-z0-9_ -]{2,25})\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)$', line)
        if m:
            k = m.group(1).strip().lower().replace(' ', '_').replace('-', '_')
            if k not in metrics:
                try:
                    metrics[k] = float(m.group(2))
                except ValueError:
                    pass
    return metrics

def format_duration(seconds):
    if seconds is None:
        return "N/A"
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    rem = seconds % 60
    return f"{minutes}m {rem:.1f}s"

def cmd_report(args):
    with open(args.results_json, 'r', encoding='utf-8') as f:
        runs_data = json.load(f)

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)
    primary_metric = (args.primary_metric or 'accuracy').lower()

    for r in runs_data:
        out_log = r.get('output_log')
        res_file = r.get('result_file')
        out_text = ""
        res_text = ""
        if out_log and os.path.isfile(out_log):
            try:
                with open(out_log, 'r', encoding='utf-8', errors='replace') as f:
                    out_text = f.read()
            except Exception:
                pass
        if res_file and os.path.isfile(res_file):
            try:
                with open(res_file, 'r', encoding='utf-8', errors='replace') as f:
                    res_text = f.read()
            except Exception:
                pass

        parsed = parse_metrics(out_text, res_text)
        if 'metrics' not in r or not r['metrics']:
            r['metrics'] = parsed
        else:
            r['metrics'].update(parsed)

    param_keys = []
    metric_keys_set = set()
    for r in runs_data:
        for p in r.get('params', {}).keys():
            if p not in param_keys:
                param_keys.append(p)
        for m in r.get('metrics', {}).keys():
            metric_keys_set.add(m)
    metric_keys = sorted(list(metric_keys_set))

    def sort_score(r):
        status_rank = 1 if r.get('status') == 'Success' else 0
        metric_val = r.get('metrics', {}).get(primary_metric)
        if metric_val is not None and isinstance(metric_val, (int, float)):
            return (status_rank, metric_val, -r.get('duration_sec', 999999))
        return (status_rank, -999999, -r.get('duration_sec', 999999))

    sorted_runs = sorted(runs_data, key=sort_score, reverse=True)
    successful = [r for r in runs_data if r.get('status') == 'Success']
    best_run = sorted_runs[0] if successful else (sorted_runs[0] if sorted_runs else None)

    # 1. CSV Summary
    csv_file = os.path.join(output_dir, 'benchmark_summary.csv')
    fieldnames = ['run_id', 'status', 'duration_sec'] + param_keys + metric_keys + ['output_log', 'result_file']
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in runs_data:
            row = {
                'run_id': r['run_id'],
                'status': r.get('status', 'Unknown'),
                'duration_sec': round(r.get('duration_sec', 0.0), 3),
                'output_log': r.get('output_log', ''),
                'result_file': r.get('result_file', '')
            }
            row.update(r.get('params', {}))
            row.update(r.get('metrics', {}))
            writer.writerow(row)

    # 2. JSON Summary
    json_file = os.path.join(output_dir, 'benchmark_summary.json')
    report_dict = {
        "manifest": args.manifest or "N/A",
        "total_runs": len(runs_data),
        "successful_runs": len(successful),
        "failed_runs": len(runs_data) - len(successful),
        "primary_metric": primary_metric,
        "best_run": {
            "run_id": best_run['run_id'],
            "params": best_run.get('params'),
            "metrics": best_run.get('metrics'),
            "duration_sec": best_run.get('duration_sec'),
        } if best_run and best_run.get('status') == 'Success' else None,
        "runs": runs_data
    }
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(report_dict, f, indent=2)

    # 3. Markdown Summary
    md_file = os.path.join(output_dir, 'benchmark_summary.md')
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write("# Hyperparameter Grid Search Benchmark Summary\n\n")
        f.write(f"- **Algorithm Manifest:** `{args.manifest or 'N/A'}`\n")
        f.write(f"- **Total Configurations Tested:** {len(runs_data)}\n")
        f.write(f"- **Successful Runs:** {len(successful)}\n")
        f.write(f"- **Failed Runs:** {len(runs_data) - len(successful)}\n")
        if best_run and best_run.get('status') == 'Success':
            f.write(f"- **Top-Performing Run:** `{best_run['run_id']}`\n")
            if primary_metric in best_run.get('metrics', {}):
                f.write(f"  - **{primary_metric.capitalize()}:** `{best_run['metrics'][primary_metric]}`\n")
            f.write(f"  - **Duration:** `{format_duration(best_run.get('duration_sec'))}`\n")
            f.write(f"  - **Best Parameters:** `{best_run.get('params')}`\n\n")
        else:
            f.write("\n")

        headers = ['Rank', 'Run ID', 'Status', 'Duration'] + param_keys + metric_keys
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("| " + " | ".join(['---'] * len(headers)) + " |\n")
        for rank, r in enumerate(sorted_runs, 1):
            row = [
                str(rank),
                r['run_id'],
                r.get('status', 'Unknown'),
                format_duration(r.get('duration_sec')),
            ]
            for p in param_keys:
                row.append(str(r.get('params', {}).get(p, '')))
            for m in metric_keys:
                row.append(str(r.get('metrics', {}).get(m, '-')))
            f.write("| " + " | ".join(row) + " |\n")

    # 4. Formatted Terminal Table
    print("\n" + "="*80)
    print("                 GRID SEARCH BENCHMARK RESULTS SUMMARY")
    print("="*80)
    print(f"Total Runs: {len(runs_data)} | Successful: {len(successful)} | Failed: {len(runs_data) - len(successful)}")
    if best_run and best_run.get('status') == 'Success':
        score_str = f"{primary_metric}={best_run.get('metrics', {}).get(primary_metric, 'N/A')}"
        print(f"Top Configuration: {best_run['run_id']} ({score_str}, duration={format_duration(best_run.get('duration_sec'))})")
        print(f"Best Parameters: {best_run.get('params')}")
    print("-"*80)

    display_cols = ['Run ID', 'Status', 'Duration'] + param_keys[:4]
    if primary_metric in metric_keys and primary_metric not in display_cols:
        display_cols.append(primary_metric)
    for m in metric_keys[:2]:
        if m not in display_cols:
            display_cols.append(m)

    col_widths = {c: len(c) for c in display_cols}
    for r in sorted_runs:
        for c in display_cols:
            val = ""
            if c == 'Run ID': val = r['run_id']
            elif c == 'Status': val = r.get('status', '')
            elif c == 'Duration': val = format_duration(r.get('duration_sec'))
            elif c in param_keys: val = str(r.get('params', {}).get(c, ''))
            elif c in metric_keys: val = str(r.get('metrics', {}).get(c, '-'))
            col_widths[c] = max(col_widths[c], len(val))

    header_line = " | ".join(c.ljust(col_widths[c]) for c in display_cols)
    sep_line = "-+-".join("-" * col_widths[c] for c in display_cols)
    print(header_line)
    print(sep_line)
    for r in sorted_runs:
        line_vals = []
        for c in display_cols:
            val = ""
            if c == 'Run ID': val = r['run_id']
            elif c == 'Status': val = r.get('status', '')
            elif c == 'Duration': val = format_duration(r.get('duration_sec'))
            elif c in param_keys: val = str(r.get('params', {}).get(c, ''))
            elif c in metric_keys: val = str(r.get('metrics', {}).get(c, '-'))
            line_vals.append(val.ljust(col_widths[c]))
        print(" | ".join(line_vals))
    print("="*80)
    print(f"Benchmark reports generated:")
    print(f"  - CSV:      {csv_file}")
    print(f"  - JSON:     {json_file}")
    print(f"  - Markdown: {md_file}\n")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command', required=True)

    gen_p = subparsers.add_parser('generate')
    gen_p.add_argument('--manifest', help='Path to manifest JSON')
    gen_p.add_argument('--manifest-json', help='Manifest JSON string')
    gen_p.add_argument('--grid', help='Path to grid JSON')
    gen_p.add_argument('--param', action='append', help='CLI parameter override name=v1,v2')
    gen_p.add_argument('--auto', action='store_true', help='Expand all choice parameters')

    prev_p = subparsers.add_parser('preview')
    prev_p.add_argument('--plan', required=True, help='Path to plan JSON file')

    rep_p = subparsers.add_parser('report')
    rep_p.add_argument('--results-json', required=True, help='Path to intermediate runs json')
    rep_p.add_argument('--output-dir', required=True, help='Path to output dir')
    rep_p.add_argument('--manifest', help='Path to manifest JSON')
    rep_p.add_argument('--primary-metric', default='accuracy', help='Metric to rank by')

    args = parser.parse_args()
    if args.command == 'generate':
        cmd_generate(args)
    elif args.command == 'preview':
        with open(args.plan, 'r', encoding='utf-8') as f:
            plan = json.load(f)
        runs = plan['runs']
        param_names = plan['parameter_names']
        print(f"Protocol: {plan.get('protocol')}")
        print(f"Total Planned Combinations: {len(runs)}\n")

        headers = ['Run ID'] + param_names + ['Arguments String']
        col_widths = {h: len(h) for h in headers}
        for r in runs:
            col_widths['Run ID'] = max(col_widths['Run ID'], len(r['run_id']))
            for p in param_names:
                col_widths[p] = max(col_widths[p], len(str(r['params'].get(p, ''))))
            col_widths['Arguments String'] = max(col_widths['Arguments String'], len(r['args_string']))

        print(' | '.join(h.ljust(col_widths[h]) for h in headers))
        print('-+-'.join('-'*col_widths[h] for h in headers))
        for r in runs:
            vals = [r['run_id'].ljust(col_widths['Run ID'])]
            for p in param_names:
                vals.append(str(r['params'].get(p, '')).ljust(col_widths[p]))
            vals.append(r['args_string'].ljust(col_widths['Arguments String']))
            print(' | '.join(vals))
    elif args.command == 'report':
        cmd_report(args)
PYTHON_ENGINE_SCRIPT
}

# ------------------------------------------------------------------------------
# Default Configuration & CLI Option Defaults
# ------------------------------------------------------------------------------
MANIFEST_FILE=""
GRID_FILE=""
CLI_PARAMS=()
AUTO_GRID=false
DRY_RUN=false
VERBOSE=false

EXEC_MODE=""
API_URL="${BACKEND_LOCAL_URL:-http://localhost:8000}"
API_USER="${PICARD_USER:-}"
API_PASS="${PICARD_PASSWORD:-}"
SCRIPT_ID=""
SCRIPT_NAME=""
DATASET_ID=""
DATASET_NAME=""
POLL_INTERVAL=3
EXPERIMENT_TIMEOUT=3600

SCRIPT_FILE=""
DATASET_FILE=""
MAIN_CLASS=""
SPARK_MASTER="${SPARK_MASTER_URL:-spark://spark-master:7077}"
DOCKER_CONTAINER="spark-master"
CMD_TEMPLATE=""

OUTPUT_DIR=""
PRIMARY_METRIC="accuracy"

# ------------------------------------------------------------------------------
# CLI Argument Parsing
# ------------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    -m|--manifest)
      MANIFEST_FILE="$2"
      shift 2
      ;;
    --manifest=*)
      MANIFEST_FILE="${1#*=}"
      shift
      ;;
    -g|--grid)
      GRID_FILE="$2"
      shift 2
      ;;
    --grid=*)
      GRID_FILE="${1#*=}"
      shift
      ;;
    -p|--param)
      CLI_PARAMS+=("$2")
      shift 2
      ;;
    --param=*)
      CLI_PARAMS+=("${1#*=}")
      shift
      ;;
    -a|--auto)
      AUTO_GRID=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --mode)
      EXEC_MODE="$2"
      shift 2
      ;;
    --mode=*)
      EXEC_MODE="${1#*=}"
      shift
      ;;
    -u|--url)
      API_URL="$2"
      shift 2
      ;;
    --url=*)
      API_URL="${1#*=}"
      shift
      ;;
    --username|--user)
      API_USER="$2"
      shift 2
      ;;
    --username=*|--user=*)
      API_USER="${1#*=}"
      shift
      ;;
    --password|--pass)
      API_PASS="$2"
      shift 2
      ;;
    --password=*|--pass=*)
      API_PASS="${1#*=}"
      shift
      ;;
    -s|--script-id)
      SCRIPT_ID="$2"
      shift 2
      ;;
    --script-id=*)
      SCRIPT_ID="${1#*=}"
      shift
      ;;
    --script-name)
      SCRIPT_NAME="$2"
      shift 2
      ;;
    --script-name=*)
      SCRIPT_NAME="${1#*=}"
      shift
      ;;
    -d|--dataset-id)
      DATASET_ID="$2"
      shift 2
      ;;
    --dataset-id=*)
      DATASET_ID="${1#*=}"
      shift
      ;;
    --dataset-name)
      DATASET_NAME="$2"
      shift 2
      ;;
    --dataset-name=*)
      DATASET_NAME="${1#*=}"
      shift
      ;;
    --poll-interval)
      POLL_INTERVAL="$2"
      shift 2
      ;;
    --timeout)
      EXPERIMENT_TIMEOUT="$2"
      shift 2
      ;;
    --script-file)
      SCRIPT_FILE="$2"
      shift 2
      ;;
    --dataset-file)
      DATASET_FILE="$2"
      shift 2
      ;;
    --main-class)
      MAIN_CLASS="$2"
      shift 2
      ;;
    --spark-master)
      SPARK_MASTER="$2"
      shift 2
      ;;
    --docker-container)
      DOCKER_CONTAINER="$2"
      shift 2
      ;;
    --cmd-template)
      CMD_TEMPLATE="$2"
      shift 2
      ;;
    -o|--output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --output-dir=*)
      OUTPUT_DIR="${1#*=}"
      shift
      ;;
    --metric)
      PRIMARY_METRIC="$2"
      shift 2
      ;;
    -v|--verbose)
      VERBOSE=true
      shift
      ;;
    *)
      log_error "Unknown option: $1 (Run with --help to see available options)"
      exit 1
      ;;
  esac
done

API_URL="${API_URL%/}"

# Determine default execution mode if not specified
if [[ -z "$EXEC_MODE" ]]; then
  if [[ -n "$SCRIPT_ID" || -n "$SCRIPT_NAME" || -n "$API_USER" ]]; then
    EXEC_MODE="api"
  elif [[ -n "$SCRIPT_FILE" ]]; then
    EXEC_MODE="direct"
  else
    EXEC_MODE="api"
  fi
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="benchmark_results_${TIMESTAMP}"
fi

# Cleanup handlers
COOKIE_JAR=""
cleanup() {
  if [[ -n "$COOKIE_JAR" && -f "$COOKIE_JAR" ]]; then
    rm -f "$COOKIE_JAR"
  fi
}
trap cleanup EXIT INT TERM

log_step "Initializing PICARD Hyperparameter Grid Search"
log_info "Mode:               ${BOLD}${EXEC_MODE}${RESET}"
log_info "Output Directory:   ${OUTPUT_DIR}"
log_info "Primary Metric:     ${PRIMARY_METRIC}"

# ------------------------------------------------------------------------------
# Mode API Setup & Authentication
# ------------------------------------------------------------------------------
CSRF_TOKEN=""
MANIFEST_JSON_PAYLOAD=""

if [[ "$EXEC_MODE" == "api" && "$DRY_RUN" == "false" ]] || [[ "$EXEC_MODE" == "api" && -z "$MANIFEST_FILE" ]]; then
  if ! command -v curl >/dev/null 2>&1; then
    log_error "cURL is required for API mode. Please install curl or use direct mode."
    exit 1
  fi

  COOKIE_JAR=$(mktemp 2>/dev/null || echo "/tmp/picard_cookies_${TIMESTAMP}.txt")

  log_info "Connecting to PICARD API at ${API_URL}..."

  # Login if credentials provided
  if [[ -n "$API_USER" ]]; then
    log_info "Authenticating user '${API_USER}'..."
    LOGIN_RESP=$(curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
      -H "Content-Type: application/json" \
      -d "{\"username\": \"${API_USER}\", \"password\": \"${API_PASS}\"}" \
      "${API_URL}/auth/user_login/")
    
    if [[ "$LOGIN_RESP" == *"login failed"* ]]; then
      log_error "Authentication failed for user '${API_USER}'. Check username and password."
      exit 1
    fi
    log_success "Authentication successful."
  fi

  # Retrieve Session & CSRF Token
  SESSION_RESP=$(curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" "${API_URL}/auth/session/")
  CSRF_TOKEN=$("$PYTHON_BIN" -c "import sys, json; print(json.loads(sys.stdin.read()).get('csrfToken', ''))" <<< "$SESSION_RESP" 2>/dev/null || echo "")

  # Auto-resolve Script ID and Manifest if --script-name given
  if [[ -n "$SCRIPT_NAME" ]]; then
    log_info "Looking up script by name: '${SCRIPT_NAME}'..."
    SCRIPTS_JSON=$(curl -s -b "$COOKIE_JAR" "${API_URL}/scripts/")
    SCRIPT_MATCH=$("$PYTHON_BIN" -c "
import sys, json
scripts = json.loads(sys.stdin.read())
target = '$SCRIPT_NAME'.strip().lower()
matched = next((s for s in scripts if s.get('name', '').strip().lower() == target or s.get('id', '') == '$SCRIPT_NAME'), None)
if matched:
    print(json.dumps(matched))
else:
    sys.exit(1)
" <<< "$SCRIPTS_JSON" 2>/dev/null || echo "")

    if [[ -z "$SCRIPT_MATCH" ]]; then
      log_error "Could not find registered script matching '${SCRIPT_NAME}' on ${API_URL}."
      exit 1
    fi

    SCRIPT_ID=$("$PYTHON_BIN" -c "import json; print(json.loads('''$SCRIPT_MATCH''')['id'])")
    log_success "Resolved Script ID: ${SCRIPT_ID}"

    # Extract manifest if not supplied locally
    if [[ -z "$MANIFEST_FILE" ]]; then
      MANIFEST_JSON_PAYLOAD=$("$PYTHON_BIN" -c "
import json
script = json.loads('''$SCRIPT_MATCH''')
cfg = script.get('algorithm_config')
if cfg:
    print(json.dumps(cfg))
" 2>/dev/null || echo "")
      if [[ -n "$MANIFEST_JSON_PAYLOAD" ]]; then
        log_success "Retrieved algorithm manifest directly from PICARD script record."
      fi
    fi
  elif [[ -n "$SCRIPT_ID" && -z "$MANIFEST_FILE" ]]; then
    # Fetch scripts list to find config for script_id
    SCRIPTS_JSON=$(curl -s -b "$COOKIE_JAR" "${API_URL}/scripts/")
    MANIFEST_JSON_PAYLOAD=$("$PYTHON_BIN" -c "
import sys, json
scripts = json.loads(sys.stdin.read())
matched = next((s for s in scripts if s.get('id') == '$SCRIPT_ID'), None)
if matched and matched.get('algorithm_config'):
    print(json.dumps(matched['algorithm_config']))
" <<< "$SCRIPTS_JSON" 2>/dev/null || echo "")
  fi

  # Auto-resolve Dataset ID if --dataset-name given
  if [[ -n "$DATASET_NAME" ]]; then
    log_info "Looking up dataset by name: '${DATASET_NAME}'..."
    DATASETS_JSON=$(curl -s -b "$COOKIE_JAR" "${API_URL}/datasets/")
    DATASET_ID=$("$PYTHON_BIN" -c "
import sys, json
datasets = json.loads(sys.stdin.read())
target = '$DATASET_NAME'.strip().lower()
matched = next((d for d in datasets if d.get('name', '').strip().lower() == target or d.get('file_name', '').strip().lower() == target or d.get('id') == '$DATASET_NAME'), None)
if matched:
    print(matched['id'])
else:
    sys.exit(1)
" <<< "$DATASETS_JSON" 2>/dev/null || echo "")

    if [[ -z "$DATASET_ID" ]]; then
      log_error "Could not find registered dataset matching '${DATASET_NAME}' on ${API_URL}."
      exit 1
    fi
    log_success "Resolved Dataset ID: ${DATASET_ID}"
  fi
fi

# Ensure manifest source is present
if [[ -z "$MANIFEST_FILE" && -z "$MANIFEST_JSON_PAYLOAD" ]]; then
  log_error "No algorithm manifest specified! Use --manifest <file.json> or provide --script-name in API mode."
  exit 1
fi

if [[ -n "$MANIFEST_FILE" && ! -f "$MANIFEST_FILE" ]]; then
  log_error "Manifest file not found: $MANIFEST_FILE"
  exit 1
fi

if [[ -n "$GRID_FILE" && ! -f "$GRID_FILE" ]]; then
  log_error "Grid specification file not found: $GRID_FILE"
  exit 1
fi

# ------------------------------------------------------------------------------
# Grid Generation & Parameter Validation
# ------------------------------------------------------------------------------
log_step "Validating Parameters & Building Hyperparameter Grid"

ENGINE_GEN_ARGS=("generate")
if [[ -n "$MANIFEST_FILE" ]]; then
  ENGINE_GEN_ARGS+=("--manifest" "$MANIFEST_FILE")
else
  ENGINE_GEN_ARGS+=("--manifest-json" "$MANIFEST_JSON_PAYLOAD")
fi

if [[ -n "$GRID_FILE" ]]; then
  ENGINE_GEN_ARGS+=("--grid" "$GRID_FILE")
fi

for param_override in "${CLI_PARAMS[@]}"; do
  ENGINE_GEN_ARGS+=("--param" "$param_override")
done

if [[ "$AUTO_GRID" == "true" ]]; then
  ENGINE_GEN_ARGS+=("--auto")
fi

# Generate grid plan
mkdir -p "$OUTPUT_DIR"
PLAN_FILE="$OUTPUT_DIR/.plan.json"
run_python_engine "${ENGINE_GEN_ARGS[@]}" > "$PLAN_FILE"
TOTAL_COMBOS=$("$PYTHON_BIN" -c "import json; print(json.load(open('$PLAN_FILE', encoding='utf-8'))['total_combinations'])")

log_success "Parameter validation successful. Total configurations generated: ${BOLD}${TOTAL_COMBOS}${RESET}"

# If Dry-Run, print preview and exit
if [[ "$DRY_RUN" == "true" ]]; then
  log_step "Dry-Run Mode: Previewing Planned Parameter Combinations"
  run_python_engine preview --plan "$PLAN_FILE"
  echo ""
  log_info "Dry-run complete. No experiments were executed."
  exit 0
fi

# ------------------------------------------------------------------------------
# Prepare Output Directory & Run Environment
# ------------------------------------------------------------------------------
mkdir -p "$OUTPUT_DIR/runs"
STATE_FILE="$OUTPUT_DIR/.runs_state.json"
echo "[]" > "$STATE_FILE"

# Save manifest and grid copies in output directory for provenance
if [[ -n "$MANIFEST_FILE" && -f "$MANIFEST_FILE" ]]; then
  cp "$MANIFEST_FILE" "$OUTPUT_DIR/algorithm_manifest.json"
elif [[ -n "$MANIFEST_JSON_PAYLOAD" ]]; then
  echo "$MANIFEST_JSON_PAYLOAD" > "$OUTPUT_DIR/algorithm_manifest.json"
fi

if [[ -n "$GRID_FILE" && -f "$GRID_FILE" ]]; then
  cp "$GRID_FILE" "$OUTPUT_DIR/grid_spec.json"
fi

# ------------------------------------------------------------------------------
# Execution Loop
# ------------------------------------------------------------------------------
log_step "Executing Grid Search Benchmark Runs (${TOTAL_COMBOS} total)"

RUN_INDEX=0

while read -r RUN_PAYLOAD; do
  [[ -z "$RUN_PAYLOAD" ]] && continue
  RUN_INDEX=$((RUN_INDEX + 1))

  # Parse fields safely via Python and tab separation
  IFS=$'\t' read -r RUN_ID ARGS_STRING PARAMS_JSON < <("$PYTHON_BIN" - "$RUN_PAYLOAD" << 'PY_FIELDS'
import sys, json
r = json.loads(sys.argv[1])
print(f"{r['run_id']}\t{r['args_string']}\t{json.dumps(r['params'])}")
PY_FIELDS
)

  RUN_DIR="$OUTPUT_DIR/runs/${RUN_ID}"
  mkdir -p "$RUN_DIR"
  echo "$PARAMS_JSON" > "$RUN_DIR/params.json"

  OUTPUT_LOG="$RUN_DIR/output.log"
  RESULT_FILE="$RUN_DIR/result.txt"
  RUN_STATUS="Failed"

  echo -e "\n${BOLD}${MAGENTA}--------------------------------------------------------------------------------${RESET}"
  echo -e "${BOLD}[RUN ${RUN_INDEX}/${TOTAL_COMBOS}]${RESET} ID: ${BOLD}${RUN_ID}${RESET}"
  echo -e "Parameters: ${CYAN}${ARGS_STRING}${RESET}"
  echo -e "${BOLD}${MAGENTA}--------------------------------------------------------------------------------${RESET}"

  START_TIME=$(get_timestamp_sec)

  # ============================================================================
  # MODE 1: PICARD REST API Execution
  # ============================================================================
  if [[ "$EXEC_MODE" == "api" ]]; then
    if [[ -z "$SCRIPT_ID" ]]; then
      log_error "Script ID is required in API mode. Set --script-id or --script-name."
      exit 1
    fi
    if [[ -z "$DATASET_ID" ]]; then
      log_error "Dataset ID is required in API mode. Set --dataset-id or --dataset-name."
      exit 1
    fi

    RUN_PAYLOAD_BODY="{\"dataset_id\": \"${DATASET_ID}\", \"args\": \"${ARGS_STRING}\"}"
    SUBMIT_URL="${API_URL}/experiments/run/${SCRIPT_ID}/"

    CURL_HEADERS=(-H "Content-Type: application/json")
    if [[ -n "$CSRF_TOKEN" ]]; then
      CURL_HEADERS+=(-H "X-CSRFToken: ${CSRF_TOKEN}")
    fi

    SUBMIT_RESP=$(curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" "${CURL_HEADERS[@]}" \
      -d "$RUN_PAYLOAD_BODY" "$SUBMIT_URL")

    EXPERIMENT_ID=$("$PYTHON_BIN" -c "import sys, json; print(json.loads(sys.stdin.read()).get('experiment_id', ''))" <<< "$SUBMIT_RESP" 2>/dev/null || echo "")

    # Handle duplicate 409 conflict
    if [[ -z "$EXPERIMENT_ID" && "$SUBMIT_RESP" == *"already queued or running"* ]]; then
      EXPERIMENT_ID=$("$PYTHON_BIN" -c "import sys, json; print(json.loads(sys.stdin.read()).get('experiment_id', ''))" <<< "$SUBMIT_RESP" 2>/dev/null || echo "")
      log_warn "Active experiment with these identical settings is already running. Monitoring ID: ${EXPERIMENT_ID}"
    fi

    if [[ -z "$EXPERIMENT_ID" ]]; then
      log_error "Failed to queue experiment. Response: ${SUBMIT_RESP}"
      echo "API Submission Error: ${SUBMIT_RESP}" > "$OUTPUT_LOG"
      RUN_STATUS="Failed"
    else
      log_info "Queued experiment ID: ${EXPERIMENT_ID}. Monitoring progress..."
      
      POLL_START=$(get_timestamp_sec)
      while true; do
        POLL_RESP=$(curl -s -b "$COOKIE_JAR" "${API_URL}/experiments/${EXPERIMENT_ID}/")
        EXP_STATUS=$("$PYTHON_BIN" -c "import sys, json; print(json.loads(sys.stdin.read()).get('status', 'Unknown'))" <<< "$POLL_RESP" 2>/dev/null || echo "Unknown")

        if [[ "$VERBOSE" == "true" ]]; then
          echo -ne "  Status: ${EXP_STATUS}\r"
        fi

        if [[ "$EXP_STATUS" == "Success" || "$EXP_STATUS" == "Failed" ]]; then
          RUN_STATUS="$EXP_STATUS"
          # Save live output log
          "$PYTHON_BIN" -c "import sys, json; print(json.loads(sys.stdin.read()).get('output', ''))" <<< "$POLL_RESP" > "$OUTPUT_LOG" 2>/dev/null || true

          # If success, download result artifact
          if [[ "$EXP_STATUS" == "Success" ]]; then
            curl -s -b "$COOKIE_JAR" "${API_URL}/experiments/${EXPERIMENT_ID}/result/" -o "$RESULT_FILE" 2>/dev/null || true
          fi
          break
        fi

        # Check timeout
        NOW=$(get_timestamp_sec)
        ELAPSED=$("$PYTHON_BIN" -c "print(float('$NOW') - float('$POLL_START'))")
        if (( $(echo "$ELAPSED > $EXPERIMENT_TIMEOUT" | bc -l 2>/dev/null || echo "0") )); then
          log_error "Experiment ${EXPERIMENT_ID} timed out after ${EXPERIMENT_TIMEOUT}s."
          RUN_STATUS="Timeout"
          break
        fi

        sleep "$POLL_INTERVAL"
      done
    fi

  # ============================================================================
  # MODE 2: Direct Local or Spark-Submit Execution
  # ============================================================================
  elif [[ "$EXEC_MODE" == "direct" ]]; then
    if [[ -z "$SCRIPT_FILE" || ! -f "$SCRIPT_FILE" ]]; then
      log_error "Script file not found: '$SCRIPT_FILE'. Set with --script-file."
      exit 1
    fi
    if [[ -z "$DATASET_FILE" || ! -f "$DATASET_FILE" ]]; then
      log_error "Dataset file not found: '$DATASET_FILE'. Set with --dataset-file."
      exit 1
    fi

    TEMP_RESULT_DIR="$RUN_DIR/spark_out"
    mkdir -p "$TEMP_RESULT_DIR"

    # Build command adhering to classification protocol:
    # <script> <dataset> <result_parent_dir> <result_name> <parameters...>
    SPARK_CMD=("spark-submit" "--master" "$SPARK_MASTER" "--deploy-mode" "client")
    if [[ -n "$MAIN_CLASS" ]]; then
      SPARK_CMD+=("--class" "$MAIN_CLASS")
    fi
    SPARK_CMD+=("$SCRIPT_FILE" "$DATASET_FILE" "$RUN_DIR" "spark_out")

    # Append arguments
    read -r -a ARGS_ARR <<< "$ARGS_STRING"
    SPARK_CMD+=("${ARGS_ARR[@]}")

    if [[ "$VERBOSE" == "true" ]]; then
      log_info "Executing: ${SPARK_CMD[*]}"
    fi

    set +e
    "${SPARK_CMD[@]}" > "$OUTPUT_LOG" 2>&1
    CMD_EXIT=$?
    set -e

    if [[ $CMD_EXIT -eq 0 ]]; then
      RUN_STATUS="Success"
      # Merge part-* files into result.txt if produced
      if compgen -G "${TEMP_RESULT_DIR}/part-*" > /dev/null; then
        cat "${TEMP_RESULT_DIR}"/part-* > "$RESULT_FILE" 2>/dev/null || true
      fi
    else
      RUN_STATUS="Failed"
    fi

  # ============================================================================
  # MODE 3: Docker Spark Container Execution
  # ============================================================================
  elif [[ "$EXEC_MODE" == "docker" ]]; then
    DOCKER_CMD=("docker" "exec" "-i" "$DOCKER_CONTAINER" "spark-submit" "--master" "$SPARK_MASTER")
    if [[ -n "$MAIN_CLASS" ]]; then
      DOCKER_CMD+=("--class" "$MAIN_CLASS")
    fi
    DOCKER_CMD+=("$SCRIPT_FILE" "$DATASET_FILE" "/tmp" "${RUN_ID}_out")
    read -r -a ARGS_ARR <<< "$ARGS_STRING"
    DOCKER_CMD+=("${ARGS_ARR[@]}")

    set +e
    "${DOCKER_CMD[@]}" > "$OUTPUT_LOG" 2>&1
    CMD_EXIT=$?
    set -e

    RUN_STATUS=$([[ $CMD_EXIT -eq 0 ]] && echo "Success" || echo "Failed")
  fi

  END_TIME=$(get_timestamp_sec)
  DURATION_SEC=$("$PYTHON_BIN" -c "print(round(float('$END_TIME') - float('$START_TIME'), 3))")

  if [[ "$RUN_STATUS" == "Success" ]]; then
    log_success "Run ${RUN_ID} completed successfully in $(format_time "$DURATION_SEC")."
  else
    log_error "Run ${RUN_ID} ended with status '${RUN_STATUS}' in $(format_time "$DURATION_SEC")."
  fi

  # Append run record to intermediate state JSON safely
  "$PYTHON_BIN" - "$STATE_FILE" "$RUN_ID" "$RUN_STATUS" "$DURATION_SEC" "$PARAMS_JSON" "$ARGS_STRING" "$OUTPUT_LOG" "$RESULT_FILE" << 'PY_APPEND'
import sys, json, os
state_file, run_id, status, duration, params_json, args_str, out_log, res_file = sys.argv[1:9]
with open(state_file, 'r', encoding='utf-8') as f:
    state = json.load(f)
state.append({
    'run_id': run_id,
    'status': status,
    'duration_sec': float(duration),
    'params': json.loads(params_json),
    'args_string': args_str,
    'output_log': out_log,
    'result_file': res_file if os.path.isfile(res_file) else ''
})
with open(state_file, 'w', encoding='utf-8') as f:
    json.dump(state, f, indent=2)
PY_APPEND

done < <("$PYTHON_BIN" - "$PLAN_FILE" << 'PY_ITER'
import sys, json
plan = json.load(open(sys.argv[1], encoding='utf-8'))
for r in plan['runs']:
    print(json.dumps(r))
PY_ITER
)

# ------------------------------------------------------------------------------
# Report Generation & Comparison Benchmarking
# ------------------------------------------------------------------------------
log_step "Generating Benchmark Summaries & Metric Comparisons"

run_python_engine report \
  --results-json "$STATE_FILE" \
  --output-dir "$OUTPUT_DIR" \
  --manifest "${MANIFEST_FILE:-$OUTPUT_DIR/algorithm_manifest.json}" \
  --primary-metric "$PRIMARY_METRIC"

log_success "Hyperparameter grid search benchmark completed!"
log_info "Inspect detailed reports in: ${BOLD}${OUTPUT_DIR}${RESET}"
EOF
