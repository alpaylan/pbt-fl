# itertools `MergeJoinSizeHintOverflow` (single-trial validation)

- Patch: `patches/merge_join_size_hint_overflow_9f41c18_1.patch` — `MergeJoinBy::size_hint` upper bound computes `Some(x + y)` instead of `x.checked_add(y)`.
- Ground truth: `MergeJoinBy::size_hint` in `src/merge_join.rs`
- Config: `CRABCHECK_PROFILING_MUTATIONS=100`

Single trial: pos=1, neg=100 (99% fail rate). 9647 regions total, **only 2 with `delta > 0`** (the property's Fail arm).

| Metric | Rank of src/merge_join.rs | Score |
|---|---:|---|
| all SBFL | **n/a** | filter excludes all regions where delta=0 |
| delta | n/a | same |

### Why all metrics are n/a

Every merge_join.rs region has `ef=100, ep=1, pos_avg=1.0, neg_avg=1.0` — they fire **once per test, on every test**, whether it passes or fails. The bug is a silent arithmetic error: `Some(x + y)` wraps on overflow instead of returning `None`. The *code that executes* is identical between passing and failing runs — what differs is the integer value of the returned `size_hint`, which SBFL on coverage cannot observe.

Ochiai for these regions would be `100/sqrt(100*101) = 0.995` (if computed), same as the property's Fail arm. But the default `.delta > 0` filter (which `crabcheck-profiling-analysis` uses for the human view and which our subsetting scripts inherit) drops them because `neg_avg - pos_avg = 0.0` exactly.

### Class D: silent-value bugs

This variant sits outside the A/B/C classes from the main REPORT:

- **Class A** (binary): patched line fires only on failure → good SBFL signal.
- **Class B** (cause/effect): cause fires equally, effect diverges → SBFL surfaces effect.
- **Class C** (universal-trigger): bug fires on ~all inputs → all hit regions tied.
- **Class D** (silent-value): bug changes returned values without changing control flow or hit counts → no coverage signal at all. SBFL can only identify the property's Fail arm; the code under test is invisible.

Mitigations would need to observe values, not coverage:
- Per-snapshot counter-*value* deltas (Plan C's path): doesn't help here either, since the expression only runs once.
- Instrumenting return values (e.g. Rust `#[instrument]`-style tracing): a whole different axis from SBFL.
- Differential coverage between "before the bug site" and "after": could surface `size_hint` call → checked_add vs add → both are single instructions, still no signal.

Practically: this bug class needs a DIFFERENT testing approach entirely — e.g. AFL-style value-propagation fuzzing or symbolic execution — not fault localization on test-suite coverage.
