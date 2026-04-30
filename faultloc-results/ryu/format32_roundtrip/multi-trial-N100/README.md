# ryu `Format32Roundtrip` — 10-trial rank stability at N=100

10 independent faultloc runs on the patched ryu variant. Each trial: fresh RNG → different failing seed → different mutation neighborhood. Mutation-loop bound set to 100 via `CRABCHECK_PROFILING_MUTATIONS=100`.

## Summary

| Metric | Rank stability (10 trials) |
|---|---|
| **ochiai** | rank 3 in all 10 trials — **perfectly stable** |
| **dstar** | rank 3 in all 10 trials — **perfectly stable** |
| **jaccard** | rank 3 in all 10 trials — **perfectly stable** |
| op2 | 8/10 at rank 3, 2/10 at rank 1 (tied with property) |
| delta | mode 1 (7/10), outlier at rank 11 (trial 3) |
| tarantula | rank 3-11 range, mode 3 (×3/10) — **unstable** |

Ground truth: `ryu::pretty::format32` @ `src/pretty/mod.rs:206-207`.

**Best Ochiai score**: min 0.9506, max 0.9891, mean 0.9790 (10 trials).

**Wall time**: min 3.0 s, max 4.3 s, mean 3.6 s per trial. **35.8 s total for 10 trials.**

## Takeaway

At N=100, Ochiai/Dstar/Jaccard are perfectly reproducible on this bug — every random seed places the patched function at rank 3 (behind only the two property-Fail regions). Tarantula and raw-delta are unreliable: Tarantula because its ties at 1.0 include many unrelated "hit only on failure" regions, raw-delta because hot loops dominate.

Comparison to single-trial at N=1000 (earlier measurement): same Ochiai rank (3), score 0.982 vs mean 0.979 — a 0.3% difference for 10× less compute.

Practical recommendation for this bug class: **use Ochiai with N=100**. A single trial + Ochiai rank already tells you the answer. The 10-trial experiment just confirms it's robust.

## Raw data

`trials.tsv` — one row per trial (tab-separated): `trial, seed_input, pos, neg, mut_pass, mut_fail, init_passes, wall_ms, rank_{ochiai,tarantula,dstar,jaccard,op2,delta}, best_ochiai`.

`trial_*.json` — raw `crabcheck-profiling-fast-analyze --print-json` output per trial.

## Reproduce

```bash
cd workloads/Rust/ryu
git apply patches/format32_sign_overwrite_daf6d4d_1.patch

for t in $(seq 1 10); do
  rm -rf coverage profdata && mkdir -p coverage
  CRABCHECK_PROFILING_MUTATIONS=100 LLVM_PROFILE_FILE="coverage/snapshot_%p-%m.profraw" \
    ./target/release/etna-faultloc crabcheck Format32Roundtrip 200
  crabcheck-profiling-fast-analyze coverage ryu ./target/release/etna-faultloc --print-json \
    > trial_$t.json
done

git apply -R patches/format32_sign_overwrite_daf6d4d_1.patch
```
