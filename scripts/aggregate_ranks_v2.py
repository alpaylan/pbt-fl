#!/usr/bin/env python3
"""
Corpus-wide rank aggregation for the v2 matrix (with crash-stack prior).

For every variant in matrix_jobs.tsv whose matrix-N1000 dir contains v2.done:
  - Load each of 6 config JSONs (N{100,500,1000} x init={with,without})
  - Load coverage panic_locations.jsonl from the same dir (may be absent)
  - Compute function-level ranks for {ochiai, delta, avg_norm_od, prior_only,
    prior + ochiai, prior + avg_norm_od}
  - Write per-record entries to matrix_ranks_v2.jsonl
  - Print top-N + MRR aggregates by config x method

Imports the panic-parsing + ranking helpers from compute_faultloc_ranks /
aggregate_ranks / batch_crash_prior so the prior semantics stay in lockstep.
"""
import json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
RESULTS = ROOT / "faultloc-results"
WORKLOADS = ROOT / "workloads" / "Rust"
JOBS_TSV = ROOT / "scripts" / "matrix_jobs.tsv"

sys.path.insert(0, str(ROOT / "scripts"))
from compute_faultloc_ranks import (
    parse_etna_tasks, resolve_truth, aggregate_functions,
    region_matches, sbfl_key,
)
from aggregate_ranks import normalize_metric, rank_per_metric, truth_rank_via_score
from batch_crash_prior import parse_panic_locs, region_panic_score

CONFIGS = [
    ("N100", "with"),  ("N100", "without"),
    ("N500", "with"),  ("N500", "without"),
    ("N1000", "with"), ("N1000", "without"),
]

def load_jobs():
    with open(JOBS_TSV) as f:
        rows = [line.rstrip("\n").split("\t") for line in f.readlines()[1:]]
    return [dict(zip(["workload", "property", "short", "kind_arg", "extra"], r + [""] * (5 - len(r))))
            for r in rows if len(r) >= 4]

def per_config_ranks(regions, truths, panic_locs):
    grouped = aggregate_functions(regions)
    out = {"n_groups": len(grouped), "n_panic_overlap_groups": 0}
    if not grouped or not truths:
        return out
    N = len(grouped)
    panic_overlap = [region_panic_score(g, panic_locs) for g in grouped]
    out["n_panic_overlap_groups"] = sum(panic_overlap)
    no = normalize_metric(grouped, "ochiai")
    nd = normalize_metric(grouped, "delta")
    avg = [(no[i] + nd[i]) / 2.0 for i in range(N)]
    ochiai_score = [-rank_per_metric(grouped, "ochiai")[i] for i in range(N)]
    delta_score = [-rank_per_metric(grouped, "delta")[i] for i in range(N)]
    out["ochiai"]        = truth_rank_via_score(grouped, ochiai_score, truths)
    out["delta"]         = truth_rank_via_score(grouped, delta_score, truths)
    out["avg_norm_od"]   = truth_rank_via_score(grouped, avg, truths)
    out["prior_only"]    = truth_rank_via_score(grouped, panic_overlap, truths)
    out["prior_avg"]     = truth_rank_via_score(grouped, [panic_overlap[i] * 10 + avg[i] for i in range(N)], truths)
    out["prior_ochiai"]  = truth_rank_via_score(grouped, [panic_overlap[i] * 1e6 + ochiai_score[i] for i in range(N)], truths)
    return out

def confidence_band(rec):
    """Pre-truth confidence label. Returns (band, rule_fired). Calibrated against
    actual rank performance — see the stratification tables in the aggregator
    output. Bands order: HIGH > MEDIUM > MEDIUM_LOW > LOW_MEDIUM > LOW."""
    n_overlap = rec.get("n_panic_overlap_groups", 0) or 0
    n_panics  = rec.get("n_panic_events", 0) or 0
    o, d      = rec.get("ochiai"), rec.get("delta")
    if n_overlap == 1:
        return ("HIGH", "singleton_panic_overlap")
    if o == 1 and d == 1:
        return ("HIGH", "both_metrics_rank_1")
    if o == 1 or d == 1:
        return ("MEDIUM", "one_metric_rank_1")
    if n_panics > 0 and n_overlap > 1:
        return ("MEDIUM_LOW", "panic_multi_tier")
    if o is not None and d is not None and abs(o - d) > 5:
        return ("LOW", "metrics_disagree_gt5")
    return ("LOW_MEDIUM", "default")

def main():
    rows = []
    jobs = load_jobs()
    n_no_truth = n_no_data = n_no_v2 = 0
    for j in jobs:
        w_dir = WORKLOADS / j["workload"]
        toml = w_dir / "etna.toml"
        if not toml.exists(): continue
        task = next((t for t in parse_etna_tasks(toml) if t["short"] == j["short"]), None)
        if task is None: continue
        truths = resolve_truth(w_dir, task)
        if not truths: n_no_truth += 1; continue
        out_dir = RESULTS / j["workload"] / j["short"] / "matrix-N1000"
        if not (out_dir / "v2.done").exists(): n_no_v2 += 1; continue
        panic_locs, n_panics = parse_panic_locs(out_dir / "panic_locations.jsonl")
        for n_label, init_label in CONFIGS:
            cfg_path = out_dir / f"{n_label}-{init_label}.json"
            if not cfg_path.exists() or cfg_path.stat().st_size == 0:
                n_no_data += 1; continue
            try:
                data = json.loads(cfg_path.read_text())
            except Exception:
                continue
            ranks = per_config_ranks(data.get("regions", []), truths, panic_locs)
            rec = {
                "workload": j["workload"], "variant": j["short"], "kind": task["kind"],
                "config_n": n_label, "config_init": init_label,
                "pos": data.get("positive_samples", 0), "neg": data.get("negative_samples", 0),
                "n_panic_events": n_panics, "n_panic_locs": len(panic_locs),
                **ranks,
            }
            band, rule = confidence_band(rec)
            rec["confidence"] = band
            rec["confidence_rule"] = rule
            rows.append(rec)
    out_path = RESULTS / "matrix_ranks_v2.jsonl"
    out_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"# {len(rows)} records to {out_path}")
    print(f"#   skipped: no_truth={n_no_truth} no_v2={n_no_v2} no_data={n_no_data}\n")

    by_config = defaultdict(list)
    for r in rows:
        by_config[(r["config_n"], r["config_init"])].append(r)

    methods = ["ochiai", "delta", "avg_norm_od", "prior_only", "prior_ochiai", "prior_avg"]
    print(f"{'config':<14} {'method':<13}  {'top-1':>6} {'top-5':>6} {'top-10':>6} {'top-20':>6} {'top-50':>6}  {'MRR':>5}")
    print("-" * 90)
    for cfg in CONFIGS:
        bucket = by_config[cfg]
        denom = len(bucket) or 1
        cfg_s = f"{cfg[0]}-{cfg[1]}"
        for m in methods:
            ks = [r[m] for r in bucket if r.get(m) is not None]
            if not ks: continue
            t1  = sum(1 for x in ks if x <= 1)  / denom * 100
            t5  = sum(1 for x in ks if x <= 5)  / denom * 100
            t10 = sum(1 for x in ks if x <= 10) / denom * 100
            t20 = sum(1 for x in ks if x <= 20) / denom * 100
            t50 = sum(1 for x in ks if x <= 50) / denom * 100
            mrr = sum(1.0 / x for x in ks) / denom
            tag = "*" if m.startswith("prior") else " "
            print(f"{cfg_s:<14} {m:<13}{tag} {t1:>5.1f}% {t5:>5.1f}% {t10:>5.1f}% {t20:>5.1f}% {t50:>5.1f}%  {mrr:>5.3f}")
        print()

    print("Stratified by confidence band (N1000-with), method = prior_avg:")
    band_order = ["HIGH", "MEDIUM", "MEDIUM_LOW", "LOW_MEDIUM", "LOW"]
    by_band = defaultdict(list)
    for r in by_config[("N1000", "with")]:
        by_band[r.get("confidence", "?")].append(r)
    print(f"  {'band':<12} {'n':>4}  {'top-1':>6} {'top-3':>6} {'top-10':>6}  {'MRR':>5}  {'rule(s)':<35}")
    for band in band_order:
        bucket = by_band.get(band, [])
        if not bucket: continue
        denom = len(bucket)
        rules = sorted({r.get("confidence_rule", "?") for r in bucket})
        ks = [r.get("prior_avg") for r in bucket if r.get("prior_avg") is not None]
        t1 = sum(1 for x in ks if x <= 1) / denom * 100
        t3 = sum(1 for x in ks if x <= 3) / denom * 100
        t10 = sum(1 for x in ks if x <= 10) / denom * 100
        mr = sum(1.0/x for x in ks) / denom if ks else float("nan")
        print(f"  {band:<12} {denom:>4}  {t1:>5.1f}% {t3:>5.1f}% {t10:>5.1f}%  {mr:>5.3f}  {','.join(rules):<35}")
    print()

    print("Stratified by panic-fired vs silent (N1000-with):")
    panicy = [r for r in by_config[("N1000", "with")] if r["n_panic_events"] > 0]
    silent = [r for r in by_config[("N1000", "with")] if r["n_panic_events"] == 0]
    for label, bucket in [("panic-fired", panicy), ("silent", silent)]:
        denom = len(bucket) or 1
        print(f"  {label} (n={len(bucket)})")
        for m in methods:
            ks = [r[m] for r in bucket if r.get(m) is not None]
            if not ks: continue
            t1 = sum(1 for x in ks if x<=1)/denom*100
            t5 = sum(1 for x in ks if x<=5)/denom*100
            t10 = sum(1 for x in ks if x<=10)/denom*100
            mrr = sum(1.0/x for x in ks)/denom
            print(f"    {m:<13}  t1={t1:>4.1f}% t5={t5:>4.1f}% t10={t10:>4.1f}%  MRR={mrr:.3f}")
        print()

if __name__ == "__main__":
    main()
