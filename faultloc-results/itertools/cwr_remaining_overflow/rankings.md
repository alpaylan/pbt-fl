# itertools `CwrSizeHintOverflow` (single-trial validation)

- Patch: `patches/cwr_remaining_overflow_c13ee58_1.patch` — reverts `remaining_for` in combinations_with_replacement from a two-branch form (n=0 ⇒ `k.saturating_sub(1)`, else `(n-1).checked_add(k)?`) to the one-liner `checked_binomial((n+k).saturating_sub(1), k)`. With `n = usize::MAX` and `k ≥ 2`, `n + k` overflows.
- Ground truth: `remaining_for` in `src/combinations_with_replacement.rs`
- Config: `CRABCHECK_PROFILING_MUTATIONS=100`

Single trial: pos=0, neg=101 (**100% fail rate**). 9640 regions total, 100 with `delta > 0`.

| Metric | Rank of src/combinations_with_replacement.rs | Score | Line |
|---|---:|---:|---:|
| ochiai | 55 (tied at 1.0) | 1.0 | 202 |
| tarantula | 55 (tied) | 1.0 | 202 |
| dstar | 55 | 1.8e308 | 202 |
| jaccard | 55 | 1.0 | 202 |
| op2 | 55 | 101 | 202 |
| **delta** | **1** | **2.0** | **202** (exact patched line) |

Top Ochiai: all in `size_hint.rs:25-27` — `size_hint::add_scalar` — the scalar-overflow helper called by the patched `remaining_for`. Classic effect-dominates-cause at the Ochiai level.

**Class C-count with exceptional delta behavior**: delta rank 1 points **exactly at the patched line** (`remaining_for` @ line 202) while SBFL ties 55 regions at Ochiai 1.0. This is the cleanest Class C-count case we've seen: the bug happens in a specific math path that fires a predictable number of times per test, and the buggy version's control flow through `(n+k).saturating_sub(1)` vs. the fixed `(n-1).checked_add(k)?` creates a per-snapshot count difference that delta picks up at the exact source location.

If you're doing automated triage on this workload: **report delta's top-1 first** — for this bug class it's the right answer while SBFL's top-55 is a soup of size-hint helpers.
