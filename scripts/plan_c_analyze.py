#!/usr/bin/env python3
"""
Plan C proof-of-concept: per-snapshot region counts → distribution-aware
discriminators (Mann-Whitney U, Welch's t, KS).

Usage:
  plan_c_analyze.py <workload_dir> <module> <truth_file> <truth_start>-<truth_end>
e.g.:
  plan_c_analyze.py workloads/Rust/ordered-float ordered_float src/lib.rs 2175-2185

Compares the rank of the buggy function under each new metric to the existing
ochiai/delta ranks computed from the same data.
"""
import json, subprocess, sys, math, statistics, time
from pathlib import Path
from collections import defaultdict

if len(sys.argv) != 5:
    print(__doc__); sys.exit(2)
WORKLOAD_DIR = Path(sys.argv[1]).resolve()
MODULE       = sys.argv[2]
TRUTH_FILE   = sys.argv[3]
TRUTH_START, TRUTH_END = map(int, sys.argv[4].split("-"))

BIN = WORKLOAD_DIR / "target/release/etna-faultloc"
INDICES = WORKLOAD_DIR / "coverage/indices.json"
PROFDATA_DIR = WORKLOAD_DIR / "profdata"

assert BIN.exists() and INDICES.exists() and PROFDATA_DIR.exists(), \
    f"Run instrumented + N=100 first; missing one of {BIN}, {INDICES}, {PROFDATA_DIR}"

idx = json.loads(INDICES.read_text())
positives = idx["positives"]   # snapshot indices that passed
negatives = idx["negatives"]   # snapshot indices that failed
print(f"# {len(positives)} positive snapshots, {len(negatives)} negative")

# ---------- step 1: build per-region per-snapshot count matrix ----------
# Region key: (file_relative, function_mangled, sl, sc, el, ec)
# counts[key] = dict[snapshot_idx -> count]
counts = defaultdict(dict)
snapshot_label = {}  # snapshot_idx -> "pos" | "neg"
for s in positives: snapshot_label[s] = "pos"
for s in negatives: snapshot_label[s] = "neg"

t0 = time.time()
for s in sorted(snapshot_label):
    pd = PROFDATA_DIR / f"snapshot_iteration_{s}.profdata"
    if not pd.exists(): continue
    res = subprocess.run(
        ["llvm-cov", "export", str(BIN), f"--instr-profile={pd}", "--format=text", "--skip-expansions"],
        capture_output=True, check=True
    )
    cov = json.loads(res.stdout)
    for fn in cov["data"][0]["functions"]:
        if MODULE not in fn["name"]:
            continue  # only keep regions inside the workload's crate
        fname = fn["filenames"][0]
        for r in fn["regions"]:
            sl, sc, el, ec, count = r[0], r[1], r[2], r[3], r[4]
            key = (fname, fn["name"], sl, sc, el, ec)
            counts[key][s] = count
print(f"# llvm-cov export pass: {time.time()-t0:.1f}s, {len(counts)} regions")

# ---------- step 2: per-region statistics ----------
all_pos = sorted(positives)
all_neg = sorted(negatives)

def split_counts(c_dict):
    pos = [c_dict.get(s, 0) for s in all_pos]
    neg = [c_dict.get(s, 0) for s in all_neg]
    return pos, neg

def welch_t(pos, neg):
    """Welch's t-statistic (no scipy)."""
    nP, nN = len(pos), len(neg)
    if nP < 2 or nN < 2: return 0.0
    mP, mN = statistics.mean(pos), statistics.mean(neg)
    vP = statistics.variance(pos) if len(set(pos)) > 1 else 0.0
    vN = statistics.variance(neg) if len(set(neg)) > 1 else 0.0
    denom = math.sqrt(vP/nP + vN/nN)
    if denom == 0: return 0.0
    return (mN - mP) / denom

def mann_whitney_u(pos, neg):
    """U-statistic for neg > pos. No tie-break correction; ranks averaged."""
    nP, nN = len(pos), len(neg)
    if nP == 0 or nN == 0: return 0.0
    combined = sorted([(v, "pos") for v in pos] + [(v, "neg") for v in neg])
    # Average rank for ties
    ranks = {}
    i = 0
    while i < len(combined):
        j = i
        while j+1 < len(combined) and combined[j+1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-indexed
        for k in range(i, j+1):
            ranks[k] = avg_rank
        i = j+1
    R_neg = sum(ranks[k] for k, (v, lbl) in enumerate(combined) if lbl == "neg")
    U_neg = R_neg - nN*(nN+1)/2
    # Standardize to a comparable score — fraction of all (pos, neg) pairs where neg > pos
    return U_neg / (nP * nN)

def ks_stat(pos, neg):
    """Kolmogorov-Smirnov: max gap between ECDFs."""
    if not pos or not neg: return 0.0
    all_vals = sorted(set(pos) | set(neg))
    nP, nN = len(pos), len(neg)
    max_d = 0.0
    for v in all_vals:
        cP = sum(1 for x in pos if x <= v) / nP
        cN = sum(1 for x in neg if x <= v) / nN
        d = abs(cP - cN)
        if d > max_d: max_d = d
    return max_d

def ochiai_binary(pos, neg):
    """Reference: classical ochiai over binary hit/miss."""
    ef = sum(1 for x in neg if x > 0)
    ep = sum(1 for x in pos if x > 0)
    nP, nN = len(pos), len(neg)
    nf = nN - ef
    if (ef + ep) == 0 or ef + nf == 0: return 0.0
    return ef / math.sqrt((ef+nf) * (ef+ep))

def delta_avg(pos, neg):
    """Reference: delta = mean(neg) - mean(pos)."""
    mP = statistics.mean(pos) if pos else 0.0
    mN = statistics.mean(neg) if neg else 0.0
    return mN - mP

# Compute scores
scores = {}
for key, c_dict in counts.items():
    pos, neg = split_counts(c_dict)
    scores[key] = {
        "ochiai":    ochiai_binary(pos, neg),
        "delta":     delta_avg(pos, neg),
        "welch_t":   welch_t(pos, neg),
        "u_stat":    mann_whitney_u(pos, neg),
        "ks":        ks_stat(pos, neg),
        # |u_stat - 0.5| measures separation regardless of direction
        "u_signed":  abs(mann_whitney_u(pos, neg) - 0.5),
    }

# ---------- step 3: aggregate to function level (max metric) ----------
fn_scores = defaultdict(dict)
fn_truth = {}
for key, sc in scores.items():
    fname, fn_name, sl, sc_col, el, ec = key
    fn_key = (fname, fn_name)
    overlaps_truth = (
        fname.endswith(TRUTH_FILE)
        and not (el < TRUTH_START or sl > TRUTH_END)
    )
    if overlaps_truth:
        fn_truth[fn_key] = True
    cur = fn_scores[fn_key]
    for k, v in sc.items():
        if k not in cur or v > cur[k]:
            cur[k] = v

print(f"# {len(fn_scores)} functions, {sum(fn_truth.values())} overlap truth")

# ---------- step 4: rank functions by each metric ----------
def rank_truth(metric):
    """Return (rank, score, n_total)."""
    sorted_fns = sorted(fn_scores.items(), key=lambda kv: -kv[1][metric])
    for r, (fn_key, sc) in enumerate(sorted_fns, start=1):
        if fn_truth.get(fn_key):
            return r, sc[metric], len(sorted_fns)
    return None, None, len(sorted_fns)

print()
print(f"{'metric':<10} {'rank':>6} {'score':>10}  {'n_fns':>6}  notes")
print("-" * 70)
for m in ["ochiai", "delta", "welch_t", "u_stat", "u_signed", "ks"]:
    r, sc, n = rank_truth(m)
    note = ""
    if m == "ochiai":   note = "binary hit/miss (current SBFL)"
    elif m == "delta":  note = "mean(neg) - mean(pos)"
    elif m == "welch_t":note = "(mean_neg - mean_pos) / sqrt(var/N)"
    elif m == "u_stat": note = "P(neg > pos) over all pairs"
    elif m == "u_signed":note= "|U - 0.5| (any-direction separation)"
    elif m == "ks":     note = "max gap between ECDFs"
    rs = f"{r}" if r else "—"
    sv = f"{sc:.4f}" if sc is not None else "—"
    print(f"{m:<10} {rs:>6} {sv:>10}  {n:>6}  {note}")

print()
print("Truth function(s) ranked at the above positions:")
for fn_key in fn_truth:
    print(f"  {fn_key[1][:80]}  in  {Path(fn_key[0]).name}")
