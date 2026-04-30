#!/usr/bin/env python3
"""
Compute fault-localization rank with a crash-stack prior layered on top of an
SBFL/aggregator score. The prior boosts every region whose (file, line) range
contains any location captured in coverage/panic_locations.jsonl — both the
immediate panic site (info.location()) and any frame parsed from the backtrace
that falls inside the workload tree (i.e. starts with "./src/" or matches the
workload's source root).

Combination: lexicographic — panic-overlapping regions first (sorted by
avg_norm_od within), non-overlapping after (also sorted by avg_norm_od). This
is the simplest "binary boost"; multiplicative variants are easy to swap in.

Usage:
  crash_prior_rank.py <workload_dir> <module> <truth_file>:<truth_line_lo>-<truth_line_hi> [analysis_json]

If analysis_json is omitted, runs crabcheck-profiling-fast-analyze on
<workload_dir>/coverage to produce one in-memory.

Reuses helpers from compute_faultloc_ranks.py.
"""
import json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compute_faultloc_ranks import (
    aggregate_functions, region_matches, sbfl_key,
)
from aggregate_ranks import normalize_metric, rank_per_metric, truth_rank_via_score

if len(sys.argv) < 4:
    print(__doc__); sys.exit(2)

WDIR = Path(sys.argv[1]).resolve()
MODULE = sys.argv[2]
TRUTH_SPEC = sys.argv[3]
ANALYSIS = Path(sys.argv[4]).resolve() if len(sys.argv) > 4 else None

m = re.match(r"([^:]+):(\d+)-(\d+)$", TRUTH_SPEC)
if not m:
    print(f"bad truth spec: {TRUTH_SPEC} (want file:lo-hi)"); sys.exit(2)
TRUTHS = [(m.group(1), int(m.group(2)), int(m.group(3)))]

# ---- 1. Get region scores ----
if ANALYSIS and ANALYSIS.exists():
    data = json.loads(ANALYSIS.read_text())
else:
    bin_path = WDIR / "target/release/etna-faultloc"
    cmd = ["crabcheck-profiling-fast-analyze", "coverage", MODULE, str(bin_path), "--print-json"]
    out = subprocess.run(cmd, cwd=WDIR, capture_output=True, check=True).stdout
    data = json.loads(out)

regions = data.get("regions", [])
print(f"# regions: {len(regions)}, positives: {data.get('positive_samples',0)}, negatives: {data.get('negative_samples',0)}")

# ---- 2. Load panic locations ----
PANIC_FILE = WDIR / "coverage/panic_locations.jsonl"
panic_locs = set()  # (file_relative, line)
n_panics = 0
if PANIC_FILE.exists():
    for line in PANIC_FILE.read_text().splitlines():
        if not line.strip(): continue
        n_panics += 1
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if "file" in entry and "line" in entry:
            panic_locs.add((entry["file"], int(entry["line"])))
        # Parse backtrace frames: lines like "             at <path>:<line>:<col>".
        # json.loads already turned the embedded \n escapes into real newlines.
        for bt_line in entry.get("bt", "").split("\n"):
            mm = re.search(r"at ([^\s:]+):(\d+):\d+", bt_line)
            if mm:
                fn, ln = mm.group(1), int(mm.group(2))
                # Keep frames inside the workload tree; drop std/core/rustc internals
                # AND drop the framework files (etna shim + faultloc driver) that
                # appear on every panic but are never the bug.
                if fn.startswith("./src/") or fn.startswith("src/"):
                    fn_norm = fn[2:] if fn.startswith("./") else fn
                    if fn_norm.startswith("src/bin/") or fn_norm == "src/etna.rs":
                        continue
                    panic_locs.add((fn_norm, ln))

print(f"# total panic events: {n_panics}, unique (file, line) hits: {len(panic_locs)}")
for f, l in sorted(panic_locs):
    print(f"    panic@{f}:{l}")

# ---- 3. Mark panic-overlapping regions ----
def region_panic_score(region):
    rf = region.get("file", "")
    sl, el = region.get("start_line", -1), region.get("end_line", -1)
    for pf, pl in panic_locs:
        if rf.endswith(pf) and sl <= pl <= el:
            return 1
    return 0

# Aggregate to function-level for fair comparison with the rest of the pipeline.
grouped = aggregate_functions(regions)
N = len(grouped)
panic_overlap = [region_panic_score(g) for g in grouped]
print(f"# function groups: {N}, panic-overlapping groups: {sum(panic_overlap)}")

# ---- 4. Compute baselines + prior-boosted ranks ----
def rank_via(scores):
    return truth_rank_via_score(grouped, scores, TRUTHS)

if N == 0:
    print("no regions — abort"); sys.exit(1)

# avg_norm_od baseline
no = normalize_metric(grouped, "ochiai")
nd = normalize_metric(grouped, "delta")
avg = [(no[i] + nd[i]) / 2.0 for i in range(N)]
ochiai_score = [-rank_per_metric(grouped, "ochiai")[i] for i in range(N)]

baseline_ochiai = rank_via(ochiai_score)
baseline_avg = rank_via(avg)

# Prior-boosted: lexicographic (panic_overlap desc, avg desc)
LARGE = 10.0
boosted_avg = [panic_overlap[i] * LARGE + avg[i] for i in range(N)]
boosted_ochiai = [panic_overlap[i] * 1e6 + (-rank_per_metric(grouped, "ochiai")[i]) for i in range(N)]
prior_only = [panic_overlap[i] for i in range(N)]  # tie-breaks pick the smaller-rank truth-overlap

prior_avg_rank = rank_via(boosted_avg)
prior_ochiai_rank = rank_via(boosted_ochiai)
prior_only_rank = rank_via(prior_only)

print()
print(f"{'method':<22}  {'truth_rank':>10}")
print("-" * 36)
print(f"{'ochiai (baseline)':<22}  {baseline_ochiai!r:>10}")
print(f"{'avg_norm_od':<22}  {baseline_avg!r:>10}")
print(f"{'prior_only':<22}  {prior_only_rank!r:>10}")
print(f"{'prior + ochiai':<22}  {prior_ochiai_rank!r:>10}")
print(f"{'prior + avg_norm_od':<22}  {prior_avg_rank!r:>10}")
