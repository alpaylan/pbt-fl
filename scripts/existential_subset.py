#!/usr/bin/env python3
"""
Existential proof: does there exist a subset of the captured snapshots that
makes ochiai (or another metric) rank the buggy region first?

Greedy: start with (all_pos, all_neg), repeatedly drop the one snapshot whose
removal most improves the truth's rank. Stop when no drop helps. Also run
several randomized restarts to escape local minima.

Usage:
  existential_subset.py <workload_dir> <module> <truth_file> <truth_start>-<truth_end>

Reuses the count-matrix-loading logic from plan_c_analyze.py.
"""
import json, math, random, statistics, subprocess, sys, time
from collections import defaultdict
from pathlib import Path

if len(sys.argv) != 5:
    print(__doc__); sys.exit(2)
WORKLOAD_DIR = Path(sys.argv[1]).resolve()
MODULE       = sys.argv[2]
TRUTH_FILE   = sys.argv[3]
TRUTH_START, TRUTH_END = map(int, sys.argv[4].split("-"))

BIN = WORKLOAD_DIR / "target/release/etna-faultloc"
INDICES = WORKLOAD_DIR / "coverage/indices.json"
PROFDATA_DIR = WORKLOAD_DIR / "profdata"

idx = json.loads(INDICES.read_text())
all_pos = sorted(idx["positives"])
all_neg = sorted(idx["negatives"])
print(f"# Initial pool: {len(all_pos)} pos, {len(all_neg)} neg")

# ---------- load count matrix ----------
counts = defaultdict(dict)  # key -> {snapshot_idx: count}
truth_keys = set()
all_snaps = sorted(set(all_pos) | set(all_neg))
t0 = time.time()
for s in all_snaps:
    pd = PROFDATA_DIR / f"snapshot_iteration_{s}.profdata"
    if not pd.exists(): continue
    cov = json.loads(subprocess.run(
        ["llvm-cov", "export", str(BIN), f"--instr-profile={pd}", "--format=text", "--skip-expansions"],
        capture_output=True, check=True).stdout)
    for fn in cov["data"][0]["functions"]:
        if MODULE not in fn["name"]: continue
        for r in fn["regions"]:
            sl, sc, el, ec, count = r[0], r[1], r[2], r[3], r[4]
            key = (fn["filenames"][0], fn["name"], sl, sc, el, ec)
            counts[key][s] = count
            if fn["filenames"][0].endswith(TRUTH_FILE) and not (el < TRUTH_START or sl > TRUTH_END):
                truth_keys.add(key)
print(f"# loaded {len(counts)} regions in {time.time()-t0:.1f}s, {len(truth_keys)} match truth")

# Aggregate to function level (max metric across regions of same function)
def fn_score(c_dict, pos_set, neg_set, metric):
    """Compute metric score for a single region given current pos/neg sets."""
    pos_vals = [c_dict.get(s, 0) for s in pos_set]
    neg_vals = [c_dict.get(s, 0) for s in neg_set]
    if metric == "ochiai":
        ef = sum(1 for x in neg_vals if x > 0)
        ep = sum(1 for x in pos_vals if x > 0)
        nf = len(neg_vals) - ef
        denom = math.sqrt((ef + nf) * (ef + ep)) if (ef+nf)*(ef+ep) > 0 else 0
        return ef / denom if denom > 0 else 0.0
    elif metric == "delta":
        mP = statistics.mean(pos_vals) if pos_vals else 0.0
        mN = statistics.mean(neg_vals) if neg_vals else 0.0
        return mN - mP
    return 0.0

def fn_aggregate(pos_set, neg_set, metric):
    """Build (file, fn_name) -> max_score across its regions."""
    by_fn = defaultdict(float)
    for key, c_dict in counts.items():
        fname, fn_name = key[0], key[1]
        s = fn_score(c_dict, pos_set, neg_set, metric)
        if s > by_fn[(fname, fn_name)]:
            by_fn[(fname, fn_name)] = s
    return by_fn

def truth_rank(pos_set, neg_set, metric, with_score=False):
    by_fn = fn_aggregate(pos_set, neg_set, metric)
    ordered = sorted(by_fn.items(), key=lambda kv: -kv[1])
    truth_fns = set((k[0], k[1]) for k in truth_keys)
    for r, ((fname, fn_name), score) in enumerate(ordered, start=1):
        if (fname, fn_name) in truth_fns:
            return (r, score, len(ordered)) if with_score else r
    return None if not with_score else (None, None, len(ordered))

# ---------- baseline ----------
print()
print("Baseline (all snapshots):")
for m in ["ochiai", "delta"]:
    r, s, n = truth_rank(all_pos, all_neg, m, with_score=True)
    print(f"  {m:<8} rank={r}/{n}  score={s:.4f}")

# ---------- greedy reduction ----------
def greedy_reduce(metric, start_pos, start_neg, label="greedy", verbose=False):
    pos = list(start_pos); neg = list(start_neg)
    best_r = truth_rank(pos, neg, metric)
    if best_r is None:
        return None, pos, neg
    history = [best_r]
    while True:
        improved = False
        # Try removing each pos snapshot
        best_drop = None
        best_drop_r = best_r
        best_drop_kind = None
        for s in pos:
            if len(pos) <= 1: break
            test = [x for x in pos if x != s]
            r = truth_rank(test, neg, metric)
            if r is not None and r < best_drop_r:
                best_drop_r = r; best_drop = s; best_drop_kind = "pos"
        for s in neg:
            if len(neg) <= 1: break
            test = [x for x in neg if x != s]
            r = truth_rank(pos, test, metric)
            if r is not None and r < best_drop_r:
                best_drop_r = r; best_drop = s; best_drop_kind = "neg"
        if best_drop is not None:
            if best_drop_kind == "pos": pos = [x for x in pos if x != best_drop]
            else:                       neg = [x for x in neg if x != best_drop]
            best_r = best_drop_r
            history.append(best_r)
            improved = True
            if verbose: print(f"  drop {best_drop_kind}={best_drop} -> rank {best_r} (|P|={len(pos)} |N|={len(neg)})")
        if not improved: break
        if best_r == 1: break
    return best_r, pos, neg, history

# ---------- random-restart ----------
def random_restart(metric, n_restarts=8, seed=42):
    """Random subset of pool, then greedy."""
    rng = random.Random(seed)
    best_r = None; best_pos = None; best_neg = None
    for i in range(n_restarts):
        # Drop a random fraction first
        keep_pos = rng.sample(all_pos, max(2, len(all_pos) // 2))
        keep_neg = rng.sample(all_neg, max(2, len(all_neg) // 2))
        r, p, n, _ = greedy_reduce(metric, keep_pos, keep_neg)
        if best_r is None or (r is not None and r < best_r):
            best_r = r; best_pos = p; best_neg = n
        if best_r == 1: break
    return best_r, best_pos, best_neg

# ---------- run ----------
print()
print("Greedy reduction (start = all snapshots):")
for m in ["ochiai", "delta"]:
    r, p, n, hist = greedy_reduce(m, all_pos, all_neg)
    base_r, _, _ = truth_rank(all_pos, all_neg, m, with_score=True)
    print(f"  {m:<8} baseline={base_r} -> best={r} (final |P|={len(p)} |N|={len(n)}, {len(hist)} drops)")

print()
print("Random-restart x 8 (different starting subsets):")
for m in ["ochiai", "delta"]:
    r, p, n = random_restart(m, n_restarts=8)
    print(f"  {m:<8} best across restarts = {r} (final |P|={len(p)} |N|={len(n)})")
