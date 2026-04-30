#!/usr/bin/env python3
"""
Subset coverage/indices.json to one of the 6 matrix configs:
  {N=100, 500, 1000} x {init=with, init=without}

The full run captures `max_mutations=1000` mutation snapshots [0..=1000]
plus `max_initial_passes=K` initial-sweep positives at indices
[initial_pass_base..initial_pass_base+K). Subset rules:

- max_mut: keep only mutation indices <= max_mut (failing seed at 0 stays).
- with init: keep all initial-sweep positives (>= initial_pass_base).
- without init: drop initial-sweep positives.

Usage:
  subset_indices.py <coverage_dir> <max_mut> <with_init: 0|1> <out_path>
"""
import json, sys, os

def main():
    if len(sys.argv) != 5:
        print(__doc__); sys.exit(2)
    cov_dir, max_mut, with_init, out_path = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) != 0, sys.argv[4]
    # Prefer the unmodified `indices.full.json` backup (so repeated subsetting
    # against the same coverage dir always sources the full run, not whatever
    # was last written into `indices.json`).
    full = os.path.join(cov_dir, "indices.full.json")
    src  = full if os.path.exists(full) else os.path.join(cov_dir, "indices.json")
    idx = json.load(open(src))
    cfg = idx["config"]
    init_base = cfg["initial_pass_base"]
    init_max  = cfg["max_initial_passes"]
    init_set  = set(range(init_base, init_base + init_max))

    def keep(i):
        if i in init_set:
            return with_init
        # Mutation indices: 0 (failing seed) or i in [1..=max_mutations]
        return i <= max_mut

    pos_kept, pos_ex = [], []
    for i, p in enumerate(idx["positives"]):
        if keep(p):
            pos_kept.append(p)
            if i < len(idx.get("positive_examples", [])):
                pos_ex.append(idx["positive_examples"][i])
    neg_kept, neg_ex = [], []
    for i, n in enumerate(idx["negatives"]):
        if keep(n):
            neg_kept.append(n)
            if i < len(idx.get("negative_examples", [])):
                neg_ex.append(idx["negative_examples"][i])

    out_cfg = dict(cfg)
    out_cfg["max_mutations"] = max_mut
    out_cfg["max_initial_passes"] = init_max if with_init else 0
    out = {
        "positives": pos_kept,
        "negatives": neg_kept,
        "positive_examples": pos_ex,
        "negative_examples": neg_ex,
        "config": out_cfg,
    }
    with open(out_path, "w") as f:
        json.dump(out, f)
    print(f"[subset] mut<={max_mut} init={'with' if with_init else 'without'} -> "
          f"pos={len(pos_kept)} neg={len(neg_kept)} -> {out_path}")

if __name__ == "__main__":
    main()
