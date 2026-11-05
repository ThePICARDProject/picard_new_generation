#!/usr/bin/env python3
"""
PICARD Hyperparameter Grid Search & Benchmarking Utility
Cross-platform implementation (Windows, Linux, macOS)
"""

import argparse
import csv
import glob
import http.cookiejar
import itertools
import json
import math
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


# ==============================================================================
# Parameter Normalization & Validation
# ==============================================================================
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


def build_grid_plan(manifest_data, grid_data=None, cli_params=None, auto=False):
    grid = grid_data or {}
    if cli_params:
        grid.update(cli_params)

    params = manifest_data.get('parameters', [])
    if not params:
        raise ValueError("Algorithm manifest contains no parameter definitions.")

    param_pools = []
    param_names = []
    for p in params:
        name = p['name']
        param_names.append(name)
        if name in grid:
            raw = grid[name]
            candidates = raw if isinstance(raw, list) else [raw]
        elif auto and p.get('type') == 'choice' and p.get('choices'):
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

    return {
        "protocol": manifest_data.get("protocol", "spark-classification-v1"),
        "total_combinations": len(runs),
        "parameter_names": param_names,
        "runs": runs
    }


# ==============================================================================
# Metric Parsing & Formatting
# ==============================================================================
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


# ==============================================================================
# PICARD API Client
# ==============================================================================
class PicardApiClient:
    def __init__(self, base_url, username=None, password=None):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.csrf_token = ""

    def request(self, endpoint, method="GET", data=None, headers=None):
        url = f"{self.base_url}{endpoint}"
        all_headers = headers or {}
        body = None
        if data is not None:
            all_headers["Content-Type"] = "application/json"
            if self.csrf_token:
                all_headers["X-CSRFToken"] = self.csrf_token
            body = json.dumps(data).encode('utf-8')

        req = urllib.request.Request(url, data=body, headers=all_headers, method=method)
        try:
            with self.opener.open(req) as resp:
                raw = resp.read()
                try:
                    return resp.status, json.loads(raw.decode('utf-8'))
                except Exception:
                    return resp.status, raw.decode('utf-8', errors='replace')
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode('utf-8'))
            except Exception:
                parsed = raw.decode('utf-8', errors='replace')
            return exc.code, parsed

    def authenticate(self):
        # 1. Login
        if self.username and self.password:
            status, resp = self.request("/auth/user_login/", method="POST", data={
                "username": self.username,
                "password": self.password
            })
            if status != 200:
                raise RuntimeError(f"Authentication failed for user '{self.username}': {resp}")

        # 2. Get CSRF Token from session
        status, sess = self.request("/auth/session/")
        if isinstance(sess, dict) and "csrfToken" in sess:
            self.csrf_token = sess["csrfToken"]

    def list_scripts(self):
        _, scripts = self.request("/scripts/")
        return scripts if isinstance(scripts, list) else []

    def list_datasets(self):
        _, datasets = self.request("/datasets/")
        return datasets if isinstance(datasets, list) else []

    def submit_experiment(self, script_id, dataset_id, args_string):
        status, resp = self.request(f"/experiments/run/{script_id}/", method="POST", data={
            "dataset_id": dataset_id,
            "args": args_string
        })
        return status, resp

    def get_experiment_detail(self, experiment_id):
        _, detail = self.request(f"/experiments/{experiment_id}/")
        return detail

    def download_result(self, experiment_id, dest_path):
        url = f"{self.base_url}/experiments/{experiment_id}/result/"
        req = urllib.request.Request(url, method="GET")
        try:
            with self.opener.open(req) as resp:
                with open(dest_path, 'wb') as f:
                    f.write(resp.read())
            return True
        except Exception:
            return False


# ==============================================================================
# Report Generation
# ==============================================================================
def generate_reports(runs_data, manifest_path, output_dir, primary_metric='accuracy'):
    os.makedirs(output_dir, exist_ok=True)
    primary_metric = primary_metric.lower()

    # Parse metrics from files if available
    for r in runs_data:
        out_log = r.get('output_log')
        res_file = r.get('result_file')
        out_text, res_text = "", ""
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

    # 1. CSV
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

    # 2. JSON
    json_file = os.path.join(output_dir, 'benchmark_summary.json')
    report_dict = {
        "manifest": manifest_path or "N/A",
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

    # 3. Markdown
    md_file = os.path.join(output_dir, 'benchmark_summary.md')
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write("# Hyperparameter Grid Search Benchmark Summary\n\n")
        f.write(f"- **Algorithm Manifest:** `{manifest_path or 'N/A'}`\n")
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

    # 4. Terminal Summary
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


# ==============================================================================
# Main CLI Execution
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="PICARD Hyperparameter Grid Search & Benchmarking Utility")
    parser.add_argument("-m", "--manifest", help="Path to algorithm manifest JSON file")
    parser.add_argument("-g", "--grid", help="Path to hyperparameter grid JSON file")
    parser.add_argument("-p", "--param", action="append", help="Candidate parameter override name=v1,v2,...")
    parser.add_argument("-a", "--auto", action="store_true", help="Auto-expand choice parameters to all allowed values")
    parser.add_argument("--dry-run", action="store_true", help="Preview planned combinations without running")

    parser.add_argument("--mode", choices=["api", "direct", "docker"], default="api", help="Execution backend mode")
    parser.add_argument("-u", "--url", default=os.environ.get("BACKEND_LOCAL_URL", "http://localhost:8000"), help="PICARD backend API URL")
    parser.add_argument("--username", "--user", default=os.environ.get("PICARD_USER", ""), help="PICARD login username")
    parser.add_argument("--password", "--pass", default=os.environ.get("PICARD_PASSWORD", ""), help="PICARD login password")
    parser.add_argument("-s", "--script-id", help="UUID of registered Script/Algorithm")
    parser.add_argument("--script-name", help="Display name of Script/Algorithm to auto-resolve")
    parser.add_argument("-d", "--dataset-id", help="UUID of registered CSV Dataset")
    parser.add_argument("--dataset-name", help="Display name of CSV Dataset to auto-resolve")
    parser.add_argument("--poll-interval", type=int, default=3, help="Status polling interval in seconds")
    parser.add_argument("--timeout", type=int, default=3600, help="Maximum timeout in seconds per experiment")

    parser.add_argument("--script-file", help="Path to algorithm file (.py or .jar) for direct mode")
    parser.add_argument("--dataset-file", help="Path to dataset CSV file for direct mode")
    parser.add_argument("--main-class", help="Main driver class for JAR execution")
    parser.add_argument("--spark-master", default=os.environ.get("SPARK_MASTER_URL", "spark://spark-master:7077"), help="Spark master URL")
    parser.add_argument("--docker-container", default="spark-master", help="Docker container name for docker mode")
    parser.add_argument("--cmd-template", help="Custom command template ({script}, {dataset}, {result_dir}, {result_name}, {args})")

    parser.add_argument("-o", "--output-dir", help="Directory for benchmark results")
    parser.add_argument("--metric", default="accuracy", help="Primary metric for ranking")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose debug output")

    args = parser.parse_args()

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or f"benchmark_results_{timestamp}"

    # Setup API client if needed
    api_client = None
    manifest_data = None

    if args.manifest and os.path.isfile(args.manifest):
        with open(args.manifest, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)

    if args.mode == "api":
        api_client = PicardApiClient(args.url, args.username, args.password)
        try:
            api_client.authenticate()
        except Exception as exc:
            if not args.dry_run:
                print(f"[ERROR] Could not authenticate with PICARD API: {exc}", file=sys.stderr)
                sys.exit(1)

        # Auto-resolve script if name given
        if args.script_name:
            scripts = api_client.list_scripts()
            target = args.script_name.strip().lower()
            matched = next((s for s in scripts if s.get('name', '').strip().lower() == target or s.get('id', '') == args.script_name), None)
            if matched:
                args.script_id = matched['id']
                if not manifest_data and matched.get('algorithm_config'):
                    manifest_data = matched['algorithm_config']
            else:
                print(f"[ERROR] Could not find script matching '{args.script_name}' on {args.url}", file=sys.stderr)
                sys.exit(1)

        # Auto-resolve dataset if name given
        if args.dataset_name:
            datasets = api_client.list_datasets()
            target = args.dataset_name.strip().lower()
            matched = next((d for d in datasets if d.get('name', '').strip().lower() == target or d.get('file_name', '').strip().lower() == target or d.get('id', '') == args.dataset_name), None)
            if matched:
                args.dataset_id = matched['id']
            else:
                print(f"[ERROR] Could not find dataset matching '{args.dataset_name}' on {args.url}", file=sys.stderr)
                sys.exit(1)

    if not manifest_data:
        print("[ERROR] No algorithm manifest specified. Use -m/--manifest or supply --script-name.", file=sys.stderr)
        sys.exit(1)

    # Read grid config
    grid_data = {}
    if args.grid and os.path.isfile(args.grid):
        with open(args.grid, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            if "parameters" in raw and isinstance(raw["parameters"], dict):
                grid_data = raw["parameters"]
            elif "grid" in raw and isinstance(raw["grid"], dict):
                grid_data = raw["grid"]
            else:
                grid_data = raw

    cli_params = parse_cli_params(args.param)
    plan = build_grid_plan(manifest_data, grid_data, cli_params, auto=args.auto)
    runs = plan['runs']

    print(f"\n[INFO] Mode:             {args.mode.upper()}")
    print(f"[INFO] Total Grid Runs:  {len(runs)}")
    print(f"[INFO] Output Directory: {output_dir}")

    # Dry-run preview
    if args.dry_run:
        print("\n" + "="*80)
        print("                  DRY-RUN PARAMETER MATRIX PREVIEW")
        print("="*80)
        param_names = plan['parameter_names']
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
        print("="*80)
        print("[INFO] Dry-run complete. No experiments were executed.\n")
        return

    # Create run output directory
    os.makedirs(os.path.join(output_dir, "runs"), exist_ok=True)
    with open(os.path.join(output_dir, "algorithm_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    runs_results = []

    # Execution loop
    for idx, run_info in enumerate(runs, 1):
        run_id = run_info['run_id']
        args_str = run_info['args_string']
        params = run_info['params']

        run_dir = os.path.join(output_dir, "runs", run_id)
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "params.json"), "w", encoding="utf-8") as f:
            json.dump(params, f, indent=2)

        output_log = os.path.join(run_dir, "output.log")
        result_file = os.path.join(run_dir, "result.txt")

        print("\n" + "-"*80)
        print(f"[RUN {idx}/{len(runs)}] ID: {run_id}")
        print(f"Parameters: {args_str}")
        print("-"*80)

        start_time = time.time()
        status = "Failed"

        # Mode API
        if args.mode == "api":
            if not args.script_id or not args.dataset_id:
                print("[ERROR] --script-id and --dataset-id are required in API mode.", file=sys.stderr)
                sys.exit(1)

            submit_status, submit_resp = api_client.submit_experiment(args.script_id, args.dataset_id, args_str)
            exp_id = submit_resp.get("experiment_id") if isinstance(submit_resp, dict) else None

            if not exp_id and isinstance(submit_resp, dict) and "already queued or running" in str(submit_resp):
                exp_id = submit_resp.get("experiment_id")
                print(f"[WARN] Identical experiment already active. Monitoring ID: {exp_id}")

            if not exp_id:
                print(f"[ERROR] Experiment submission failed: {submit_resp}", file=sys.stderr)
                with open(output_log, 'w', encoding='utf-8') as f:
                    f.write(f"Submission Error: {submit_resp}\n")
            else:
                print(f"[INFO] Queued experiment ID: {exp_id}. Monitoring progress...")
                poll_start = time.time()
                while True:
                    detail = api_client.get_experiment_detail(exp_id)
                    exp_status = detail.get("status", "Unknown") if isinstance(detail, dict) else "Unknown"

                    if args.verbose:
                        print(f"  Status: {exp_status}")

                    if exp_status in ("Success", "Failed"):
                        status = exp_status
                        with open(output_log, 'w', encoding='utf-8') as f:
                            f.write(detail.get("output", ""))
                        if exp_status == "Success":
                            api_client.download_result(exp_id, result_file)
                        break

                    if (time.time() - poll_start) > args.timeout:
                        print(f"[ERROR] Experiment timed out after {args.timeout}s.")
                        status = "Timeout"
                        break

                    time.sleep(args.poll_interval)

        # Mode Direct
        elif args.mode == "direct":
            if not args.script_file or not os.path.isfile(args.script_file):
                print(f"[ERROR] Script file not found: {args.script_file}", file=sys.stderr)
                sys.exit(1)
            if not args.dataset_file or not os.path.isfile(args.dataset_file):
                print(f"[ERROR] Dataset file not found: {args.dataset_file}", file=sys.stderr)
                sys.exit(1)

            temp_result_dir = os.path.join(run_dir, "spark_out")
            os.makedirs(temp_result_dir, exist_ok=True)

            if args.cmd_template:
                formatted_cmd = args.cmd_template.format(
                    script=args.script_file,
                    dataset=args.dataset_file,
                    result_dir=run_dir,
                    result_name="spark_out",
                    args=args_str
                )
                cmd = shlex.split(formatted_cmd)
            elif args.script_file.endswith(".py") and not args.main_class:
                # If running a Python script directly and spark-submit is not required / available
                import shutil
                if shutil.which("spark-submit") is not None and args.spark_master:
                    cmd = ["spark-submit", "--master", args.spark_master, "--deploy-mode", "client"]
                    cmd.extend([args.script_file, args.dataset_file, run_dir, "spark_out"])
                    cmd.extend(shlex.split(args_str))
                else:
                    cmd = [sys.executable, args.script_file, args.dataset_file, run_dir, "spark_out"]
                    cmd.extend(shlex.split(args_str))
            else:
                cmd = ["spark-submit", "--master", args.spark_master, "--deploy-mode", "client"]
                if args.main_class:
                    cmd.extend(["--class", args.main_class])
                cmd.extend([args.script_file, args.dataset_file, run_dir, "spark_out"])
                cmd.extend(shlex.split(args_str))

            if args.verbose:
                print(f"[INFO] Executing: {' '.join(cmd)}")

            with open(output_log, "w", encoding="utf-8") as out:
                proc = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT)
                if proc.returncode == 0:
                    status = "Success"
                    parts = sorted(glob.glob(os.path.join(temp_result_dir, "part-*")))
                    if parts:
                        with open(result_file, "wb") as res_f:
                            for part in parts:
                                with open(part, "rb") as p_f:
                                    res_f.write(p_f.read())
                else:
                    status = "Failed"

        duration_sec = round(time.time() - start_time, 3)
        print(f"[{status.upper()}] Run {run_id} finished in {format_duration(duration_sec)}.")

        runs_results.append({
            "run_id": run_id,
            "status": status,
            "duration_sec": duration_sec,
            "params": params,
            "args_string": args_str,
            "output_log": output_log,
            "result_file": result_file if os.path.isfile(result_file) else ""
        })

    # Generate benchmark summaries
    generate_reports(runs_results, args.manifest, output_dir, primary_metric=args.metric)


if __name__ == "__main__":
    main()
