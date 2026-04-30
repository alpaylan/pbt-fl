# aho-corasick `FindIterPrefilterParity` — 10-trial stability at N=100

Same experiment shape as ryu's 10-trial run, but on the "cause-vs-effect" bug class where we already suspected SBFL was fragile. Two configs:

- **`trials.tsv` / `trial_*.json`** — default `CRABCHECK_PROFILING_INITIAL_PASSES=100`
- **`trials_noinit.tsv` / `trial_noinit_*.json`** — `CRABCHECK_PROFILING_INITIAL_PASSES=0` (no initial-sweep positives; matches the 6-config matrix's "without init" column)

All runs use `CRABCHECK_PROFILING_MUTATIONS=100`. Ground truth: `Compiler::build_trie` @ `src/nfa/noncontiguous.rs` — and in particular the `continue 'PATTERNS;` branch at `1098:21-1098:39` that short-circuits the moved-after `prefilter.add(pat)`.

## Result: completely unstable

**Rank of `Compiler::build_trie` across 10 trials (default init=100):**

| Metric | min | max | mode | distribution |
|---|---:|---:|---:|---|
| **ochiai** | 2 | 459 | 2 (×2/10) | 375, 2, 459, 203, 214, 388, 2, 150, 207, 149 |
| tarantula | 8 | 478 | 150 (×2/10) | 398, 12, 478, 203, 220, 405, 8, 150, 207, 150 |
| dstar | 2 | 459 | 2 (×2/10) | same shape as ochiai |
| jaccard | 2 | 468 | 2 (×2/10) | same shape as ochiai |
| op2 | 2 | 459 | 2 (×2/10) | same shape as ochiai |
| delta | 10 | 447 | 56 (×1/10) | 29, 224, 56, 33, 447, 30, 183, 21, 398, 10 |

**Best Ochiai score**: min 0.42, max 0.81, mean 0.64. Standard deviation ≈ 0.13 — huge.

**With `INITIAL_PASSES=0`:**

| Metric | min | max | mode | distribution |
|---|---:|---:|---:|---|
| ochiai | 2 | 1042 | 2 (×2/10) | 1042, 595, 2, 203, 149, 149, 359, 220, 2, 204 |
| tarantula | 2 | 1076 | (no clear mode) | 1076, 632, 3, 203, 149, 150, 376, 220, 2, 224 |
| dstar | 2 | 1042 | 2 (×2/10) | same shape as ochiai |
| jaccard | 2 | 1051 | 2 (×2/10) | same shape as ochiai |
| op2 | 2 | 998 | 2 (×2/10) | same shape as ochiai |
| delta | 7 | 453 | 30 (×2/10) | 453, 76, 30, 21, 36, 15, 22, 30, 7, 24 |

Disabling initial-sweep positives doesn't help — one trial (noinit #1) blows up to rank 1042 because its 57/44 pos/neg split has so few positives hitting build_trie that the ef/ep ratio goes sideways.

## Compare to ryu

| Workload | Bug class | Ochiai rank across 10 trials |
|---|---|---|
| **ryu** `Format32Roundtrip` | binary fail on small negatives (panic path) | **3, 3, 3, 3, 3, 3, 3, 3, 3, 3** |
| **aho-corasick** `FindIterPrefilterParity` | compile-time misconfig → runtime prefilter divergence | **375, 2, 459, 203, 214, 388, 2, 150, 207, 149** |

ryu is perfectly stable because the bug has a binary execution signal: line `mod.rs:206` fires only when the property actually fails. aho-corasick's patched function runs once per test regardless of pass/fail — the signal is a count-level divergence in an inner loop, and whether that divergence shows up in any given trial depends entirely on whether the failing seed's pattern set happens to make the short-circuit branch fire differently from random positives.

## Why it's bimodal — correct seed vs. useless seed

Looking at which build_trie region ranks best in each trial:

- **Trials where rank is low (good)**: best region = `1098:21-1098:39` — the `continue 'PATTERNS;` statement, exactly the branch whose firing/not-firing determines whether the bug is triggered. Ochiai ≥ 0.80.
- **Trials where rank is high (bad)**: best region = `1118:38-1120:18` — a different spot inside build_trie whose hit signature doesn't correlate with the bug. Ochiai 0.42-0.64.

So about 20% of seeds produce a mutation neighborhood that exposes the short-circuit's pass/fail asymmetry. The other 80% don't — and you can't tell which kind you have without running the analysis.

## Practical implication

A one-shot faultloc run on this bug class is a coin flip between "rank 2 of 850+" and "rank 150-1000 of 850+". To make SBFL reliable on cause/effect bugs you need:

- Multi-seed pooling (20+ trials combined into one analysis), which stabilizes ef/ep ratios across many failing seeds, **or**
- A different localization approach that reasons about counter-expression value flow rather than binary hit coverage, **or**
- Better mutation operators that target the bug-relevant structural property (here: preserving superstring relations in the pattern set), which would make any single trial more likely to fall in the "good" 20%.

None of these are in scope for this pass, but the data is now archived so we can revisit.

## Files

- `trials.tsv`, `trial_{1..10}.json` — default init=100 config
- `trials_noinit.tsv`, `trial_noinit_{1..10}.json` — init=0 config
- Total size: ~8 MB (previously would have been ~400 GB on the old pipeline)
