# itertools `CombinationsZero` (single-trial validation)

- Patch: `patches/combinations_zero_empty_13aa10e_1.patch` — adds `self.k() == 0 ||` to the `done` check in `CombinationsGeneric::init`, and flips an empty-indices guard in `CombinationsWithReplacementGeneric::next`. Both short-circuit `combinations(0)` / `combinations_with_replacement(0)` to empty, instead of yielding `vec![vec![]]`.
- Ground truth: `CombinationsGeneric` in `src/combinations.rs`
- Config: `CRABCHECK_PROFILING_MUTATIONS=100`

Single trial: pos=0, neg=101 (**100% fail rate**). 9649 regions total, 68 with `delta > 0`.

| Metric | Rank of src/combinations.rs | Score | Line |
|---|---:|---:|---:|
| ochiai | 32 (tied at 1.0) | 1.0 | 238 |
| tarantula | 32 (tied) | 1.0 | 238 |
| dstar | 32 | 1.8e308 | 238 |
| jaccard | 32 | 1.0 | 238 |
| op2 | 32 | 101 | 238 |
| **delta** | **1** | **2.0** | **120** |

Top Ochiai: all in `lib.rs:1930-1936` — `<Range<u32> as Itertools>::combinations()` — the generic instantiation that wraps CombinationsGeneric.

**Class C-count**: 100% failure rate drags all SBFL metrics into ties at Ochiai 1.0. Delta singles out line 120 of combinations.rs — inside `CombinationsGeneric::init` where the k=0 short-circuit hits a different code path (`remaining_for` returning 0 vs 1) — at rank 1 with a 2.0 per-snapshot count divergence. This variant matches the hex `from_hex_accepts_whitespace` pattern: cause is called a variable number of times, count-aware signal picks it up cleanly, binary-hit SBFL is blind.
