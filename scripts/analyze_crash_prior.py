#!/usr/bin/env python3
"""
Analyze faultloc-results/crash_prior_sample.jsonl: stratify by panic-likely vs
not, by whether panics actually fired (n_panic_events>0), and report top-N hit
rates + per-variant improvement.
"""
import json, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
DEFAULT = ROOT / "faultloc-results" / "crash_prior_sample.jsonl"

def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("status") == "ok"]

    print(f"# {len(rows)} variants with status=ok\n")

    def panicked(r): return (r.get("n_panic_events", 0) or 0) > 0
    panicy = [r for r in rows if panicked(r)]
    silent = [r for r in rows if not panicked(r)]
    print(f"  with panics:    {len(panicy)}")
    print(f"  without panics: {len(silent)}\n")

    methods = ["ochiai_rank", "avg_norm_od_rank", "prior_only_rank", "prior_avg_rank", "prior_ochiai_rank"]
    label = {
        "ochiai_rank": "ochiai (baseline)",
        "avg_norm_od_rank": "avg_norm_od",
        "prior_only_rank": "prior_only",
        "prior_avg_rank": "prior + avg_norm",
        "prior_ochiai_rank": "prior + ochiai",
    }

    def stat(bucket, key, k):
        ks = [r[key] for r in bucket if r.get(key) is not None]
        if not ks: return float("nan")
        return sum(1 for x in ks if x <= k) / len(bucket) * 100

    def mrr(bucket, key):
        ks = [r[key] for r in bucket if r.get(key) is not None]
        if not ks: return float("nan")
        return sum(1.0 / x for x in ks) / len(bucket)

    def median(bucket, key):
        ks = sorted([r[key] for r in bucket if r.get(key) is not None])
        return ks[len(ks)//2] if ks else None

    def print_table(name, bucket):
        print(f"## {name} (n={len(bucket)})")
        print(f"{'method':<22}  {'top-1':>6} {'top-3':>6} {'top-5':>6} {'top-10':>6} {'top-20':>6}  {'MRR':>5} {'median':>6}")
        for m in methods:
            t1 = stat(bucket, m, 1); t3 = stat(bucket, m, 3); t5 = stat(bucket, m, 5)
            t10 = stat(bucket, m, 10); t20 = stat(bucket, m, 20)
            mr = mrr(bucket, m); med = median(bucket, m)
            print(f"{label[m]:<22}  {t1:>5.1f}% {t3:>5.1f}% {t5:>5.1f}% {t10:>5.1f}% {t20:>5.1f}%  {mr:>5.3f}  {str(med):>6}")
        print()

    print_table("All", rows)
    print_table("Variants where panics actually fired (prior has signal)", panicy)
    print_table("Variants without panics (prior is no-op)", silent)

    # Per-variant detail for panicked ones — show baseline vs prior side by side.
    print("## Per-variant (panicked)")
    print(f"{'workload/variant':<55} {'panics':>7} {'ochiai':>7} {'avgnorm':>8} {'prior+o':>8} {'prior+a':>8} {'pri-only':>8}")
    for r in sorted(panicy, key=lambda r: -(r.get("n_panic_events") or 0)):
        nm = f"{r['workload']}/{r['variant']}"[:54]
        print(f"{nm:<55} {r.get('n_panic_events', 0):>7} "
              f"{str(r.get('ochiai_rank')):>7} {str(r.get('avg_norm_od_rank')):>8} "
              f"{str(r.get('prior_ochiai_rank')):>8} {str(r.get('prior_avg_rank')):>8} "
              f"{str(r.get('prior_only_rank')):>8}")

if __name__ == "__main__":
    main()
