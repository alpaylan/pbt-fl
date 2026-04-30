#!/usr/bin/env python3
"""
Apply the new strict module filter to existing v2 matrix outputs and report
metrics in the format `quickcheck_with_locate!` would produce for an
end-user:

  - Share of variants whose ground-truth location is inside the top-5
    suspects under `prior + avg_norm_od`
  - False-positive HIGH: top suspect has confidence band HIGH, but the
    truth is NOT at rank 1 (we'd report the wrong line with high confidence)
  - False-negative LOW/MEDIUM: top suspect has confidence band LOW or
    MEDIUM, but truth IS at rank 1 (we'd correctly identify the bug while
    sounding underconfident)
  - Full per-band breakdown

Reuses helpers from compute_faultloc_ranks.py + aggregate_ranks_v2.py. The
strict filter mirrors the one in `crabcheck::profiling::analyze` —
demangled function name (already in the JSON's `function` field) must
start with `<module>::` after stripping a leading `<` for trait impls.
"""
import json
import sys
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


def load_jobs():
    with open(JOBS_TSV) as f:
        rows = [line.rstrip("\n").split("\t") for line in f.readlines()[1:]]
    return [dict(zip(["workload", "property", "short", "kind_arg", "extra"], r + [""] * (5 - len(r))))
            for r in rows if len(r) >= 4]


def strict_filter(regions, module):
    """Mirror crabcheck::profiling::analyze::analyze_coverage's strict_module_filter.

    Demangled function name must start with `<module>::` after stripping a
    leading `<` for trait impls.
    """
    prefix = f"{module}::"
    out = []
    for r in regions:
        f = r.get("function", "")
        trimmed = f[1:] if f.startswith("<") else f
        if trimmed.startswith(prefix):
            out.append(r)
    return out


def confidence_band_for_top_suspect(grouped, panic_overlap, ochiai_rank_of, delta_rank_of,
                                    n_panic_overlap_groups, top_idx, n_panics_total):
    """Replicate the Rust rank_with_prior band assignment for the top suspect.

    Args:
      top_idx: index of the top suspect in `grouped`.
      panic_overlap: list[bool] parallel to `grouped`.
      ochiai_rank_of, delta_rank_of: list[int] parallel to `grouped` (1-based).
    """
    po = panic_overlap[top_idx]
    o_r = ochiai_rank_of[top_idx]
    d_r = delta_rank_of[top_idx]
    if po and n_panic_overlap_groups == 1:
        return "HIGH", "singleton_panic_overlap"
    if o_r == 1 and d_r == 1:
        return "HIGH", "both_metrics_rank_1"
    if o_r == 1 or d_r == 1:
        return "MEDIUM", "one_metric_rank_1"
    if po:
        return "MEDIUM_LOW", "panic_multi_tier"
    if abs(o_r - d_r) > 5:
        return "LOW", "metrics_disagree_gt5"
    return "LOW_MEDIUM", "default"


def analyze_variant(workload, short, regions, panics, truths, n_panics_total):
    """Return a dict with rank, band, and per-suspect details for the variant."""
    if not regions or not truths:
        return {"status": "no_data" if not regions else "no_truth"}

    grouped = aggregate_functions(regions)
    if not grouped:
        return {"status": "no_groups"}
    N = len(grouped)
    panic_overlap = [region_panic_score(g, panics) for g in grouped]
    n_panic_overlap_groups = sum(panic_overlap)

    no = normalize_metric(grouped, "ochiai")
    nd = normalize_metric(grouped, "delta")
    avg = [(no[i] + nd[i]) / 2.0 for i in range(N)]
    ochiai_rk = rank_per_metric(grouped, "ochiai")
    delta_rk = rank_per_metric(grouped, "delta")

    # Sort by (panic_overlap desc, avg_norm_od desc) - same as Rust
    order = sorted(range(N), key=lambda i: (-int(panic_overlap[i]), -avg[i]))
    if not order:
        return {"status": "no_groups"}

    top_idx = order[0]
    band, rule = confidence_band_for_top_suspect(
        grouped, panic_overlap, ochiai_rk, delta_rk,
        n_panic_overlap_groups, top_idx, n_panics_total
    )

    # Truth rank under prior_avg
    truth_rank = None
    for rank, idx in enumerate(order, start=1):
        if region_matches(grouped[idx], truths):
            truth_rank = rank
            break

    # Top suspect details
    top = grouped[top_idx]
    return {
        "status": "ok",
        "n_groups": N,
        "n_panic_overlap_groups": n_panic_overlap_groups,
        "n_panics_total": n_panics_total,
        "top_suspect_file": top.get("file", ""),
        "top_suspect_function": top.get("function", ""),
        "top_suspect_lines": [top.get("start_line"), top.get("end_line")],
        "top_panic_overlap": panic_overlap[top_idx],
        "top_ochiai": top.get("suspiciousness", {}).get("ochiai", 0.0),
        "top_delta": top.get("delta", 0.0),
        "confidence": band,
        "confidence_rule": rule,
        "truth_rank": truth_rank,
        "truth_in_top_1": truth_rank == 1,
        "truth_in_top_5": truth_rank is not None and truth_rank <= 5,
    }


def main():
    rows = []
    jobs = load_jobs()
    n_no_truth = n_no_data = 0
    for j in jobs:
        w_dir = WORKLOADS / j["workload"]
        toml = w_dir / "etna.toml"
        if not toml.exists():
            continue
        task = next((t for t in parse_etna_tasks(toml) if t["short"] == j["short"]), None)
        if task is None:
            continue
        truths = resolve_truth(w_dir, task)
        if not truths:
            n_no_truth += 1
            continue
        out_dir = RESULTS / j["workload"] / j["short"] / "matrix-N1000"
        cfg_path = out_dir / "N1000-with.json"
        if not cfg_path.exists() or cfg_path.stat().st_size == 0:
            n_no_data += 1
            continue
        try:
            data = json.loads(cfg_path.read_text())
        except Exception:
            continue

        # Apply STRICT module filter (the new behavior).
        all_regions = data.get("regions", [])
        # Module name is the workload's crate name. The matrix_jobs.tsv stores
        # the workload directory name; the Rust crate name typically equals
        # the directory name with hyphens converted to underscores.
        module = j["workload"].replace("-", "_")
        strict_regions = strict_filter(all_regions, module)

        panics, n_panics_total = parse_panic_locs(out_dir / "panic_locations.jsonl")
        panics = list(panics)

        rec = analyze_variant(j["workload"], j["short"], strict_regions, panics, truths, n_panics_total)
        rec["workload"] = j["workload"]
        rec["variant"] = j["short"]
        rec["module"] = module
        rec["truth_preview"] = f"{truths[0][0]}:{truths[0][1]}-{truths[0][2]}" if truths else ""
        rec["regions_loose"] = len(all_regions)
        rec["regions_strict"] = len(strict_regions)
        rows.append(rec)

    # ---- Aggregation ----
    ok = [r for r in rows if r.get("status") == "ok"]
    print(f"# {len(ok)} variants analyzed (skipped: no_truth={n_no_truth} no_data={n_no_data})\n")

    n = len(ok) or 1
    in_top_1 = sum(1 for r in ok if r["truth_in_top_1"])
    in_top_5 = sum(1 for r in ok if r["truth_in_top_5"])
    print("## Headline (N1000-with config, strict filter, prior + avg_norm_od)")
    print(f"  Top-1 hit rate: {in_top_1}/{n} = {in_top_1/n*100:.1f}%")
    print(f"  Top-5 hit rate: {in_top_5}/{n} = {in_top_5/n*100:.1f}%")
    print()

    # ---- Per-band breakdown ----
    band_order = ["HIGH", "MEDIUM", "MEDIUM_LOW", "LOW_MEDIUM", "LOW"]
    by_band = defaultdict(list)
    for r in ok:
        by_band[r["confidence"]].append(r)

    print("## Per confidence-band breakdown")
    print(f"  {'band':<12} {'n':>4}  {'top-1':>6} {'top-5':>6}  {'rules':<60}")
    for band in band_order:
        bucket = by_band.get(band, [])
        if not bucket:
            continue
        bn = len(bucket)
        b1 = sum(1 for r in bucket if r["truth_in_top_1"])
        b5 = sum(1 for r in bucket if r["truth_in_top_5"])
        rules = sorted({r["confidence_rule"] for r in bucket})
        print(f"  {band:<12} {bn:>4}  {b1/bn*100:>5.1f}% {b5/bn*100:>5.1f}%  {','.join(rules):<60}")
    print()

    # ---- False positives in HIGH ----
    fp_high = [r for r in ok if r["confidence"] == "HIGH" and not r["truth_in_top_1"]]
    high_total = len(by_band.get("HIGH", []))
    print(f"## False-positive HIGH ({len(fp_high)} of {high_total} HIGH variants — top-1 wrong)")
    if fp_high:
        for r in fp_high:
            print(f"  - {r['workload']}/{r['variant']} (rule={r['confidence_rule']})")
            print(f"      top suspect: {r['top_suspect_function']}")
            print(f"      file:lines  {Path(r['top_suspect_file']).name}:{r['top_suspect_lines'][0]}-{r['top_suspect_lines'][1]}")
            print(f"      truth      {r['truth_preview']} (rank={r['truth_rank']})")
    else:
        print("  (none — every HIGH band correctly placed truth at rank 1)")
    print()

    # ---- False negatives in LOW + MEDIUM ----
    fn_low = [r for r in ok if r["confidence"] in ("LOW", "MEDIUM") and r["truth_in_top_1"]]
    low_med_total = len(by_band.get("LOW", [])) + len(by_band.get("MEDIUM", []))
    print(f"## False-negative LOW/MEDIUM ({len(fn_low)} of {low_med_total} LOW+MEDIUM variants — underconfident)")
    if fn_low:
        for r in fn_low[:20]:
            print(f"  - {r['workload']}/{r['variant']}  band={r['confidence']} rule={r['confidence_rule']}")
            print(f"      top suspect (correct): {r['top_suspect_function']} (rank=1)")
        if len(fn_low) > 20:
            print(f"  (+ {len(fn_low) - 20} more)")
    else:
        print("  (none — no LOW/MEDIUM band cases secretly got rank-1)")
    print()

    # ---- Strict filter impact ----
    avg_loose = sum(r["regions_loose"] for r in ok) / len(ok)
    avg_strict = sum(r["regions_strict"] for r in ok) / len(ok)
    print("## Strict filter impact")
    print(f"  Average regions per variant: {avg_loose:.0f} (loose) → {avg_strict:.0f} (strict)")
    print(f"  Reduction: {(1 - avg_strict / avg_loose) * 100:.1f}%")

    # Save full record
    out_path = RESULTS / "strict_filter_metrics.jsonl"
    out_path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"\nWrote {len(rows)} records to {out_path}")


if __name__ == "__main__":
    main()
