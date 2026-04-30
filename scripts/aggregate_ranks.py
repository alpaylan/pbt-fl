#!/usr/bin/env python3
"""
Rank-aggregation experiment: combine 6 SBFL metrics (ochiai, tarantula, dstar,
jaccard, op2, delta) via Borda count and Reciprocal Rank Fusion (RRF), and
compare against each individual metric and the min-rank oracle upper bound.

Reads the matrix JSONs at faultloc-results/<workload>/<variant>/matrix-N1000/
N{100,500,1000}-{with,without}.json. Ranks are computed at function level (max
metric value across regions of the same function) to match compute_matrix_ranks.

Outputs:
  faultloc-results/matrix_ranks_aggregated.jsonl  (per variant x config)
  stdout — top-N + MRR per (config, method).
"""
import json, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compute_faultloc_ranks import (
    parse_etna_tasks, resolve_truth, aggregate_functions, region_matches, sbfl_key,
)

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
RESULTS = ROOT / "faultloc-results"
WORKLOADS = ROOT / "workloads" / "Rust"
JOBS_TSV = ROOT / "scripts" / "matrix_jobs.tsv"

CONFIGS = [
    ("N100", "with"),  ("N100", "without"),
    ("N500", "with"),  ("N500", "without"),
    ("N1000", "with"), ("N1000", "without"),
]
METRICS = ["ochiai", "tarantula", "dstar", "jaccard", "op2", "delta"]

def load_jobs():
    out = {}
    with open(JOBS_TSV) as f:
        for line in f.readlines()[1:]:
            cols = line.rstrip("\n").split("\t")
            if len(cols) >= 3:
                out[(cols[0], cols[2])] = True
    return out

def variant_tasks():
    jobs = load_jobs()
    for w_dir in sorted(WORKLOADS.iterdir()):
        if not w_dir.is_dir(): continue
        toml = w_dir / "etna.toml"
        if not toml.exists(): continue
        for task in parse_etna_tasks(toml):
            if (w_dir.name, task["short"]) in jobs:
                yield w_dir.name, w_dir, task

def rank_per_metric(grouped, metric):
    """rank_of[i] = rank of grouped[i] under metric (1-based, dense)."""
    order = sorted(range(len(grouped)), key=lambda i: -sbfl_key(grouped[i], metric))
    rank_of = [0] * len(grouped)
    for r, i in enumerate(order, start=1):
        rank_of[i] = r
    return rank_of

def truth_rank_via_score(grouped, scores, truths):
    """Sort grouped by score (descending, higher = more suspect); find first truth match."""
    order = sorted(range(len(grouped)), key=lambda i: -scores[i])
    for r, i in enumerate(order, start=1):
        if region_matches(grouped[i], truths):
            return r
    return None

def normalize_metric(grouped, metric):
    """Per-variant min-max normalization. Returns list parallel to grouped."""
    vals = [sbfl_key(g, metric) for g in grouped]
    mx = max(vals) if vals else 0.0
    return [v / mx if mx > 0 else 0.0 for v in vals]

def aggregate(grouped, truths):
    """Return dict method -> rank_of_truth.

    The 5 SBFL metrics (ochiai/tarantula/dstar/jaccard/op2) are ~100% identical
    on this benchmark, so Borda/RRF over all 6 just majority-votes against
    delta. The orthogonal signal pair is (ochiai, delta); aggregating their
    *normalized values* (not ranks) is the win — Borda/RRF lose magnitude info.
    """
    if not grouped:
        return {}
    N = len(grouped)
    per_metric = {m: rank_per_metric(grouped, m) for m in METRICS}
    out = {m: truth_rank_via_score(grouped, [-per_metric[m][i] for i in range(N)], truths)
           for m in METRICS}

    # 6-way Borda / RRF (kept for completeness — these underperform).
    borda6 = [sum(N - per_metric[m][i] for m in METRICS) for i in range(N)]
    out["borda6"] = truth_rank_via_score(grouped, borda6, truths)
    K = 60
    rrf6 = [sum(1.0 / (K + per_metric[m][i]) for m in METRICS) for i in range(N)]
    out["rrf6"] = truth_rank_via_score(grouped, rrf6, truths)

    # 2-way (ochiai + delta) value-based aggregation. Normalize each metric to
    # [0, 1] within the variant, then take mean / max of the pair.
    no = normalize_metric(grouped, "ochiai")
    nd = normalize_metric(grouped, "delta")
    avg_norm = [(no[i] + nd[i]) / 2.0 for i in range(N)]
    max_norm = [max(no[i], nd[i]) for i in range(N)]
    out["avg_norm_od"] = truth_rank_via_score(grouped, avg_norm, truths)
    out["max_norm_od"] = truth_rank_via_score(grouped, max_norm, truths)

    # Per-variant best-metric oracle: the best rank truth achieves under any
    # single metric. Upper bound on what a metric-selection scheme could do.
    truth_per_metric_ranks = [out[m] for m in METRICS if out.get(m) is not None]
    out["oracle_metric"] = min(truth_per_metric_ranks) if truth_per_metric_ranks else None
    return out

def main():
    rows = []
    for w_name, w_dir, task in variant_tasks():
        truths = resolve_truth(w_dir, task)
        if not truths:
            continue
        for n_label, init_label in CONFIGS:
            path = RESULTS / w_name / task["short"] / "matrix-N1000" / f"{n_label}-{init_label}.json"
            if not path.exists() or path.stat().st_size == 0:
                continue
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue
            regions = data.get("regions", [])
            grouped = aggregate_functions(regions)
            ranks = aggregate(grouped, truths)
            row = {
                "workload": w_name,
                "variant": task["short"],
                "config_n": n_label,
                "config_init": init_label,
                "n_groups": len(grouped),
                **{f"{k}_fn": v for k, v in ranks.items()},
            }
            rows.append(row)

    out_path = RESULTS / "matrix_ranks_aggregated.jsonl"
    out_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"Wrote {len(rows)} records to {out_path}\n")

    by_config = defaultdict(list)
    for r in rows:
        by_config[(r["config_n"], r["config_init"])].append(r)

    headline = ["ochiai", "delta", "avg_norm_od", "max_norm_od", "borda6", "rrf6", "oracle_metric"]
    print(f"{'config':<14} {'method':<15}  {'top-1':>6} {'top-5':>6} {'top-10':>6} {'top-20':>6} {'top-50':>6}  {'MRR':>5}")
    print("-" * 90)
    for cfg in CONFIGS:
        bucket = by_config[cfg]
        denom = len(bucket) or 1
        cfg_s = f"{cfg[0]}-{cfg[1]}"
        for m in headline:
            ks = [r[f"{m}_fn"] for r in bucket if r.get(f"{m}_fn") is not None]
            if not ks: continue
            t1  = sum(1 for x in ks if x <= 1)  / denom * 100
            t5  = sum(1 for x in ks if x <= 5)  / denom * 100
            t10 = sum(1 for x in ks if x <= 10) / denom * 100
            t20 = sum(1 for x in ks if x <= 20) / denom * 100
            t50 = sum(1 for x in ks if x <= 50) / denom * 100
            mrr = sum(1.0 / x for x in ks) / denom
            tag = "*" if m in ("avg_norm_od", "max_norm_od", "oracle_metric") else " "
            print(f"{cfg_s:<14} {m:<15}{tag} {t1:>5.1f}% {t5:>5.1f}% {t10:>5.1f}% {t20:>5.1f}% {t50:>5.1f}%  {mrr:>5.3f}")
        print()

    print("Headline: avg_norm(ochiai, delta) vs the strongest single-metric baseline.")
    print(f"{'config':<14}  {'ochiai t5':>9} {'delta t5':>8} {'avg_norm t5':>11}   {'ochiai t10':>10} {'delta t10':>9} {'avg_norm t10':>12}   {'ochiai MRR':>10} {'delta MRR':>9} {'avg_norm MRR':>12}")
    for cfg in CONFIGS:
        bucket = by_config[cfg]
        denom = len(bucket) or 1
        cfg_s = f"{cfg[0]}-{cfg[1]}"
        def stat(m, k):
            ks = [r[f"{m}_fn"] for r in bucket if r.get(f"{m}_fn") is not None]
            return sum(1 for x in ks if x <= k) / denom * 100
        def mrr_of(m):
            ks = [r[f"{m}_fn"] for r in bucket if r.get(f"{m}_fn") is not None]
            return sum(1.0 / x for x in ks) / denom
        print(f"{cfg_s:<14}  {stat('ochiai', 5):>8.1f}% {stat('delta', 5):>7.1f}% {stat('avg_norm_od', 5):>10.1f}%   {stat('ochiai', 10):>9.1f}% {stat('delta', 10):>8.1f}% {stat('avg_norm_od', 10):>11.1f}%   {mrr_of('ochiai'):>10.3f} {mrr_of('delta'):>9.3f} {mrr_of('avg_norm_od'):>12.3f}")

if __name__ == "__main__":
    main()
