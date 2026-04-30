# Shrinking experiment — aho-corasick `FindIterPrefilterParity`

Hypothesis: the unstable rank on this bug class was due to random failing seeds containing noise (4-6 patterns of which only 2 matter). Running a classical QuickCheck-style shrinker before the mutation loop should reduce the seed to just the bug-relevant structure, giving a cleaner SBFL signal.

Implemented in `crabcheck::profiling::quickcheck_with_shrink` (new in this change). The shrinker for this property:

- Remove one pattern from `PatternSet` (keeping ≥ 2 so the superstring relation can survive)
- Remove one char from the haystack
- Drop the last char of one pattern (keeping each pattern ≥ 1 char)

Greedy first-improvement until local minimum. Safety cap 1000 steps.

## Result: reproducibility won, rank unchanged

### At N=100 (10 trials)

| | Ochiai rank distribution |
|---|---|
| Baseline no-shrink | `375, 2, 459, 203, 214, 388, 2, 150, 207, 149` (mode 2, spread 2-459) |
| **Shrink + N=100** | `193, 192, 193, 192, 191, 191, 191, 191, 201, 191` (mode 191 ×5, spread 191-201) |

### At N=1000 (10 trials)

| | Ochiai rank distribution |
|---|---|
| Baseline no-shrink (earlier run3 etc.) | rank 206-385 across different trials |
| **Shrink + N=1000** | `191, 191, 191, 191, 191, 191, 191, 191, 191, 191` (**mode 191 ×10/10**) |

Same story for Tarantula / Dstar / Jaccard / Op2 — all stable at 191 across all 10 trials with shrink+N=1000.

## What the "rank 191" actually is

Shrunk failing seeds converge to patterns like `(["pq", "pqr", "mn", "12"], "12")` or `(["mn", "mno", "wx", "ab"], "ab")` — 4 patterns, one superstring pair, 2-char haystack. Shrink steps: 13-45, averaging ~29.

After shrinking:
- **Property's Fail arm**: rank 1, Ochiai 1.0 (ef=47, ep=0) — fires only on failing tests. ✅ correct.
- **`packed::rabinkarp::RabinKarp::verify` + `find_at`** at rank 2-~190, Ochiai 0.72: the prefilter-verification path where the pattern-ID desync **manifests at runtime**. The effect. Fires more on failing than passing, hence high Ochiai.
- **`nfa::noncontiguous::Compiler::build_trie` @ line 1098:21-39** (the `continue 'PATTERNS;` short-circuit): rank 191, Ochiai 0.13-0.31. The root cause of the bug. Fires on almost every test (compile once per haystack, short-circuits for most mutant pattern sets too), so its ef/ep ratio is close to parity → low Ochiai.

Every trial's best build_trie region is the same line (1098:21-39). Shrinking reliably **identifies** the bug-trigger branch — you can see it by grepping for noncontiguous.rs in the output. But its absolute rank is dominated by 190 regions whose hit patterns correlate more strongly with the property outcome.

## Stability vs. absolute rank — the important takeaway

Shrinking transformed the rank distribution from bimodal-and-unstable (2-459, mode 2 ×2/10) into **unimodal-and-stable** (191, ×10/10 at N=1000). That's a qualitative improvement in reproducibility: any two runs of the pipeline on this bug now give you the same answer.

The absolute rank didn't get better because SBFL on binary hit coverage fundamentally cannot rank a cause branch above its downstream effects when the cause fires on every test. The constraint is structural, not a matter of seed quality.

What shrinking did change:
- **Before**: `build_trie` rank 2 on 20% of runs, rank 150-459 on 80%. You'd see it or you wouldn't depending on your RNG.
- **After**: `build_trie` rank 191 on every run, but always at the top of `noncontiguous.rs` regions (0.13-0.31 Ochiai), always pointing at line 1098. A tool that surfaces "top 5 non-property regions per file" would *always* land on the right line.

## Files

- `trials_shrink.tsv` + `trial_{1..10}.json` — shrink + N=100
- `trials_shrink_N1000.tsv` + `trial_N1000_{1..10}.json` — shrink + N=1000
- Total size: ~94 MB

## What would help further (not implemented)

For the root cause to rank higher, SBFL would need to distinguish "region fires with different *counter expression values*" from "region fires at all." That's the Plan C territory — an aggregator that reasons about per-snapshot counter deltas within a region rather than binary hit. Shrinking got us reproducibility; to also get absolute rank correctness on this bug class, we'd need a different localization signal.

## Follow-up: subset-tuple Mutate

Changed `crabcheck::quickcheck::Mutate` blanket impls for tuples to pick a random *non-empty subset* of components to mutate per step (was: always mutate every component). Intent: keep per-step mutations less destructive on minimal failing seeds, so more mutants preserve the bug condition.

Results: see `trials_shrink_subsetmut_N1000.tsv` + `trial_subsetmut_*.json`.

| Config | Avg fail rate | Ochiai rank | Best build_trie Ochiai |
|---|---:|---|---:|
| shrink + both-component mut + N=1000 | 3.6% | 191 (×10) | avg 0.22 |
| **shrink + subset mut + N=1000** | **14.4%** | 191-192 (mode 191) | **avg 0.44** |

The **failure rate quadrupled** (3.6% → 14.4%), which is exactly what we predicted — mutating one component at a time sometimes leaves the haystack intact (preserving the match) or leaves the patterns intact (preserving the prefix relation), so the bug condition survives much more often.

**Ochiai score on build_trie doubled** (0.22 → 0.44) since there are now enough negative samples to give the ef/ep ratio real discriminating power.

**Rank didn't change.** Still 191. The reason is unchanged: `build_trie` runs on every test (compile once per haystack), so even with perfect ef/ep discrimination, there will always be ~190 regions in `packed::rabinkarp::verify` / `find_at` / `pattern::is_prefix` / etc. that fire *disproportionately more* on failing runs (because the bug causes extra work in those paths). Those win on binary-hit SBFL.

### Conclusion of the full experimental arc

| Approach | Stability | Absolute rank | Ochiai confidence |
|---|---|---|---|
| No intervention | unstable (2-459) | sometimes rank 2 | varies wildly |
| + Shrink seed | stable (191) | consistent but bad | low (0.22) |
| + Subset-tuple Mutate | stable (191) | same | **moderate (0.44)** |

Shrink + subset-mut is the right operational default for this bug class: you always get the same answer, and the top build_trie region (line 1098 `continue 'PATTERNS;`) scores reasonably well. But the final blocker — "rank the cause above the effect" — is a SBFL-on-binary-hits structural limitation, not something the mutation operator can overcome.
