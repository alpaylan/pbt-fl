#!/usr/bin/env python3
"""
Aggregate fault-localization ranks across the 6-config matrix run.

For each variant in matrix_jobs.tsv, read every
  faultloc-results/<workload>/<variant>/matrix-N1000/N{100,500,1000}-{with,without}.json
compute the rank of the buggy function under each SBFL metric + delta, and
produce two outputs:

  1. faultloc-results/matrix_ranks.jsonl — one record per (variant, config)
     with all metric ranks at function level.
  2. stdout — top-N hit rates and MRR for each (config, metric) pair so you
     can compare e.g. ochiai@N=100,init=with vs ochiai@N=1000,init=without.

Reuses the truth-resolution helpers from compute_faultloc_ranks.py.
"""
import json, re, sys
from pathlib import Path

# Reuse helpers
sys.path.insert(0, str(Path(__file__).parent))
from compute_faultloc_ranks import (
    parse_patch_truth, parse_etna_tasks, resolve_truth,
    rank_by, rank_by_function,
)

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
RESULTS = ROOT / "faultloc-results"
WORKLOADS = ROOT / "workloads" / "Rust"
JOBS_TSV = ROOT / "scripts" / "matrix_jobs.tsv"

CONFIGS = [
    ("N100", "with"),    ("N100", "without"),
    ("N500", "with"),    ("N500", "without"),
    ("N1000", "with"),   ("N1000", "without"),
]
METRICS = ["ochiai", "tarantula", "dstar", "jaccard", "op2", "delta"]

def load_jobs():
    """Map (workload, short) -> True from matrix_jobs.tsv (header skipped)."""
    out = {}
    with open(JOBS_TSV) as f:
        for line in f.readlines()[1:]:
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 3:
                out[(cols[0], cols[2])] = True
    return out

def variant_tasks():
    """Yield (workload_name, workload_dir, task_dict) for every matrix-jobs entry."""
    jobs = load_jobs()
    for w_dir in sorted(WORKLOADS.iterdir()):
        if not w_dir.is_dir(): continue
        toml = w_dir / "etna.toml"
        if not toml.exists(): continue
        for task in parse_etna_tasks(toml):
            if (w_dir.name, task["short"]) in jobs:
                yield w_dir.name, w_dir, task

def compute_ranks_for_config(workload_dir, short, truths, n_label, init_label):
    """Read the matrix JSON for one config and return a rank dict."""
    path = RESULTS / workload_dir.name / short / "matrix-N1000" / f"{n_label}-{init_label}.json"
    if not path.exists() or path.stat().st_size == 0:
        return {"status": "missing"}
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        return {"status": f"parse-err: {e}"}
    regions = data.get("regions", [])
    out = {
        "status": "ok",
        "pos": data.get("positive_samples", 0),
        "neg": data.get("negative_samples", 0),
        "n_regions": len(regions),
    }
    if not truths:
        return out
    for metric in METRICS:
        out[f"{metric}_region"] = rank_by(regions, truths, metric)
        out[f"{metric}_fn"] = rank_by_function(regions, truths, metric)
    return out

def main():
    rows = []
    for w_name, w_dir, task in variant_tasks():
        truths = resolve_truth(w_dir, task)
        for n_label, init_label in CONFIGS:
            r = compute_ranks_for_config(w_dir, task["short"], truths, n_label, init_label)
            r["workload"] = w_name
            r["variant"] = task["short"]
            r["kind"] = task["kind"]
            r["config_n"] = n_label
            r["config_init"] = init_label
            r["truth_hunks"] = len(truths)
            rows.append(r)

    out_path = RESULTS / "matrix_ranks.jsonl"
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(rows)} matrix-rank records to {out_path}")
    print(f"  ({len(rows) // 6} variants × 6 configs)\n")

    # Aggregate: per-config top-N hit rates and MRR for the function-level
    # ranks. Denominator is the number of variants for which the config
    # produced ok status AND we have ground truth.
    print("Function-level rank aggregates by (config, metric):")
    print(f"{'config':<14} {'metric':<11} {'N':>4}  {'top-1':>6} {'top-5':>6} {'top-10':>6} {'top-20':>6} {'top-50':>6} {'top-100':>6}  {'MRR':>5}  {'median':>6}")
    print("-" * 110)

    by_config = {}
    for r in rows:
        if r.get("status") != "ok": continue
        if r.get("truth_hunks", 0) == 0: continue
        by_config.setdefault((r["config_n"], r["config_init"]), []).append(r)

    for (n_label, init_label) in CONFIGS:
        bucket = by_config.get((n_label, init_label), [])
        denom = len(bucket) or 1
        config_str = f"{n_label}-{init_label}"
        for metric in METRICS:
            key = f"{metric}_fn"
            ranks = [r[key] for r in bucket if r.get(key) is not None]
            if not ranks:
                continue
            top1  = sum(1 for x in ranks if x <=   1) / denom * 100
            top5  = sum(1 for x in ranks if x <=   5) / denom * 100
            top10 = sum(1 for x in ranks if x <=  10) / denom * 100
            top20 = sum(1 for x in ranks if x <=  20) / denom * 100
            top50 = sum(1 for x in ranks if x <=  50) / denom * 100
            top100= sum(1 for x in ranks if x <= 100) / denom * 100
            mrr   = sum(1/x for x in ranks) / denom
            median = sorted(ranks)[len(ranks)//2]
            print(f"{config_str:<14} {metric:<11} {denom:>4}  {top1:>5.1f}% {top5:>5.1f}% {top10:>5.1f}% {top20:>5.1f}% {top50:>5.1f}% {top100:>5.1f}%  {mrr:>5.3f}  {median:>6}")
        print()

    # Compact comparison: ochiai_fn top-10 across all 6 configs, side by side.
    print("Compact: ochiai_fn top-10 by config:")
    for (n_label, init_label) in CONFIGS:
        bucket = by_config.get((n_label, init_label), [])
        ranks = [r["ochiai_fn"] for r in bucket if r.get("ochiai_fn") is not None]
        denom = len(bucket) or 1
        top10 = sum(1 for x in ranks if x <= 10) / denom * 100
        print(f"  {n_label}-{init_label:<8}  top-10 = {top10:>5.1f}%   (n={denom}, found={len(ranks)})")

if __name__ == "__main__":
    main()
