#!/usr/bin/env python3
"""
Aggregate the full-suite locate run (faultloc-results/locate_full_suite.jsonl
produced by `run_locate_full_suite.py`) into the requested headline metrics:

- Share of variants whose truth location is in the top-5 suspects
- False-positive HIGH (top suspect has HIGH confidence, but truth not at rank 1)
- False-negative LOW/MEDIUM (top suspect has LOW/MEDIUM band, but truth IS at rank 1)
- Per-band breakdown
- Per-status (ok / no_locate_output / apply_failed / etc.) counts
- Per-diagnostic counts
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
RESULTS = ROOT / "faultloc-results" / "locate_full_suite.jsonl"


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    print(f"# {len(rows)} variants in {path}\n")

    # Status breakdown
    status_counter = Counter(r.get("status", "?") for r in rows)
    print("## Per-status counts")
    for status, n in status_counter.most_common():
        print(f"  {status:<24} {n:>4}")
    print()

    ok = [r for r in rows if r.get("status") == "ok"]
    if not ok:
        print("(no ok rows yet)")
        return
    no_truth = [r for r in rows if r.get("status") == "no_truth"]
    print(f"## OK rows (n={len(ok)}; no_truth excluded: {len(no_truth)})\n")

    # Top-1 / top-5 hit rate
    in_top_1 = [r for r in ok if r.get("truth_in_top_1")]
    in_top_5 = [r for r in ok if r.get("truth_in_top_5")]
    print("## Headline")
    print(f"  Top-1 hit rate: {len(in_top_1)}/{len(ok)} = {len(in_top_1) / len(ok) * 100:.1f}%")
    print(f"  Top-5 hit rate: {len(in_top_5)}/{len(ok)} = {len(in_top_5) / len(ok) * 100:.1f}%")
    print()

    # Per-band breakdown
    band_order = ["HIGH", "MEDIUM", "MEDIUM_LOW", "LOW_MEDIUM", "LOW", None]
    by_band = defaultdict(list)
    for r in ok:
        by_band[r.get("top_confidence")].append(r)

    print("## Per confidence-band breakdown")
    print(f"  {'band':<12} {'n':>4}  {'top-1':>6} {'top-5':>6}  rules")
    for band in band_order:
        bucket = by_band.get(band, [])
        if not bucket:
            continue
        bn = len(bucket)
        b1 = sum(1 for r in bucket if r.get("truth_in_top_1"))
        b5 = sum(1 for r in bucket if r.get("truth_in_top_5"))
        rules = sorted({r.get("top_confidence_rule") or "?" for r in bucket})
        rules_s = ",".join(rules)
        label = band or "?"
        print(f"  {label:<12} {bn:>4}  {b1 / bn * 100:>5.1f}% {b5 / bn * 100:>5.1f}%  {rules_s}")
    print()

    # FP HIGH
    fp_high = [r for r in ok if r.get("top_confidence") == "HIGH" and not r.get("truth_in_top_1")]
    high_total = len(by_band.get("HIGH", []))
    print(f"## False-positive HIGH ({len(fp_high)} of {high_total} HIGH variants — truth not at rank 1)")
    for r in fp_high:
        print(f"  - {r['workload']}/{r['variant']}  rule={r.get('top_confidence_rule')}")
        print(f"      top suspect: {r.get('top_function')}")
        print(f"      file:lines  {Path(r.get('top_file', '')).name}:{r.get('top_lines', [None, None])[0]}-{r.get('top_lines', [None, None])[1]}")
        print(f"      truth      {r.get('truth_preview')} (rank={r.get('truth_rank_post_prior')})")
    print()

    # FN LOW/MEDIUM
    fn_lm = [
        r
        for r in ok
        if r.get("top_confidence") in ("LOW", "MEDIUM") and r.get("truth_in_top_1")
    ]
    lm_total = sum(len(by_band.get(b, [])) for b in ("LOW", "MEDIUM"))
    print(f"## False-negative LOW/MEDIUM ({len(fn_lm)} of {lm_total} LOW+MEDIUM variants — top-1 was correct, band sounded underconfident)")
    for r in fn_lm[:30]:
        print(
            f"  - {r['workload']}/{r['variant']}  band={r.get('top_confidence')} "
            f"rule={r.get('top_confidence_rule')}"
        )
    if len(fn_lm) > 30:
        print(f"  (+ {len(fn_lm) - 30} more)")
    print()

    # Diagnostics summary
    diag_counter = Counter()
    for r in ok:
        for d in r.get("diagnostics", []):
            diag_counter[d] += 1
    if diag_counter:
        print("## Diagnostics emitted (out of OK rows)")
        for d, n in diag_counter.most_common():
            print(f"  {d:<32} {n:>4}")
        print()

    # Per-workload top-5 hit rate (compact)
    by_workload = defaultdict(list)
    for r in ok:
        by_workload[r["workload"]].append(r)
    print("## Per-workload top-5 hit rate")
    for w in sorted(by_workload.keys()):
        bucket = by_workload[w]
        top5 = sum(1 for r in bucket if r.get("truth_in_top_5"))
        print(f"  {w:<24} {top5}/{len(bucket)} = {top5 / len(bucket) * 100:>5.1f}%")


if __name__ == "__main__":
    main()
