# Fault localization on PBT-found bugs — experimental report

Consolidated write-up of the experiments under `faultloc-results/`. Scope: apply BST-style coverage-instrumented fault localization to 4 etna-ify Rust workloads (aho-corasick, crc32fast, hex, ryu), measure rank and stability of each patched function under various pipeline configurations, and document the bug-class taxonomy that emerged.

## Pipeline (final form)

Single binary, no shell scripts:

```bash
cd workloads/Rust/<crate>
git apply patches/<variant>.patch          # or: marauders set --variant <id>
mkdir -p coverage
CARGO_INCREMENTAL=0 RUSTFLAGS="-C instrument-coverage -C link-dead-code \
  -C codegen-units=1 -C inline-threshold=0 -C llvm-args=-inline-threshold=0 \
  -C debuginfo=2" cargo build --release --bin etna-faultloc [--features etna]
LLVM_PROFILE_FILE="coverage/snapshot_%p-%m.profraw" \
  ./target/release/etna-faultloc crabcheck <PropertyName> 200
crabcheck-profiling-fast-analyze coverage <module> ./target/release/etna-faultloc --print-json > out.json
```

`crabcheck-profiling-fast-analyze` reads `coverage/indices.json`, lazily merges each referenced `.profraw` to `.profdata`, spawns `llvm-cov export` per snapshot, streams output into a per-region counter hashmap (rayon P=8), demangles, emits JSON matching the legacy `crabcheck-profiling-analysis --print-json` shape. No intermediate `jsondata/` files on disk — the historical 20 GB/trial footprint is now ~230 MB/trial.

### Runtime knobs (env vars, all optional)

| Var | Default | Purpose |
|---|---:|---|
| `CRABCHECK_PROFILING_MUTATIONS` | 1000 | Mutation-loop bound |
| `CRABCHECK_PROFILING_INITIAL_PASSES` | 100 | Cap on initial-sweep positive snapshots |
| `CRABCHECK_PROFILING_RANDOM_ITERS` | 20000 | Outer random-sweep bound |
| `CRABCHECK_PROFILING_MAX_SHRINK_STEPS` | 1000 | Shrink-loop safety cap |

`indices.json` records the chosen values in its `config` field so downstream subsetting scripts never hardcode label-space assumptions.

### Profiling-loop semantics

`crabcheck::profiling::quickcheck_with_shrink(f, shrink)`:

1. Outer random sweep (`N` draws via `T::generate`). Passing iterations count; up to `K` of them take snapshots (indices `initial_pass_base..initial_pass_base+K`).
2. On first failure, apply the user-supplied `shrink` greedily until no candidate fails. Take `iteration_0` snapshot on the shrunk seed.
3. Mutation loop: for `i in 1..=M`, apply `T::mutate(&seed, rng, …)`, snapshot `iteration_i`, bucket into positives/negatives.
4. Write `coverage/indices.json` + return.

Plain `quickcheck(f)` is now `quickcheck_with_shrink(f, |_| Vec::new())`.

### The tuple-Mutate blanket

`Mutate<(T1, T2, …)>` picks a random **non-empty subset** of components per step (was: always mutate every component). For a 2-tuple, each of `{mut T1, mut T2, mut both}` is uniformly 1/3. Gives per-step mutations a chance to leave bug-relevant structure intact — critical on shrunken seeds where every component is load-bearing.

## Workloads + variants surveyed

| Crate | Variant | Injection | Property input type |
|---|---|---|---|
| aho-corasick | `replace_all_utf8_safe` | patch | `(BytePatterns, Utf8Haystack, ShortRepl)` |
| aho-corasick | `find_iter_prefilter_parity` | patch | `(PatternSet, MixHaystack)` |
| crc32fast | `combine_zero_length_identity` | marauders | `CombineZeroInput` struct of `(u32, u32)` |
| hex | `from_hex_accepts_whitespace` | marauders | `WhitespaceInput` struct of `(Vec<u8>, u32, u8)` |
| hex | `invalid_char_display_raw` | marauders | `ByteInput(u8)` |
| ryu | `format32_sign_overwrite` | patch | `F32(f32)` |

## Bug class taxonomy

Three classes emerged from the experiments, each with distinct SBFL behavior:

### Class A: Binary-signal bugs

Patched code fires *only* on failing inputs; passing inputs take a different code path.

**Examples:** aho-corasick `ReplaceAllUtf8Safe` (panic on UTF-8 split), ryu `Format32Roundtrip` (panic in `format_finite` + formatted string fails to parse back).

**Behavior:** every SBFL metric correctly surfaces the patched region at rank 2-5 (rank 1 is the property's Fail arm itself). Ochiai score ~1.0 (ef = total failing, ep = 0). **Stable across RNG seeds** — ryu gave rank 3 on every one of 10 trials with Ochiai min 0.95, max 0.99.

**Recommendation:** N=100 mutations is sufficient. `crabcheck-profiling-fast-analyze` alone, no shrink needed.

### Class B: Cause/effect bugs

Patched code fires on *every* input; the bug causes a *behavioral divergence* downstream that shows up as different code paths or counter values further along the pipeline.

**Example:** aho-corasick `FindIterPrefilterParity`. `Compiler::build_trie` runs on every test (compile twice per haystack, once with prefilter on and once off); the bug causes short-circuited patterns to miss prefilter registration, which only surfaces as divergence when `find_iter` later consults the wrong packed-prefilter pattern ID. Result: SBFL ranks the **downstream effect** (`packed::rabinkarp::verify` / `find_at` / `is_prefix` — the prefilter lookup path) above the cause (`build_trie::continue 'PATTERNS;`).

**Behavior without mitigations:** rank distribution is bimodal — 20% of RNG seeds give rank 2 (good), 80% give rank 150-459 (bad). Unreproducible.

**With shrink alone:** rank stabilizes at 191 across all seeds. The right *line* is identified (always `noncontiguous.rs:1098:21-1098:39`, the short-circuit), but the ~190 regions ranked above it are all in the downstream prefilter path. Reproducibility: ×10/10. Ochiai on the cause: ~0.22.

**With shrink + subset-tuple Mutate:** failure rate of the mutation neighborhood climbs from 3.6% → 14.4% (4×). Ochiai on the cause ~doubles (0.22 → 0.44). Rank: unchanged at 191.

**Recommendation:** shrink + subset-tuple-Mutate is the correct operational default; rank-in-file is actionable; global rank is structurally capped by SBFL-on-binary-hits. See `aho-corasick/find_iter_prefilter_parity/multi-trial-N100/shrink/README.md` for the full arc.

### Class C: Near-universal-trigger bugs

Bug triggers on ≥99.9% of random inputs, so the mutation neighborhood around any failing seed is uniformly failing (0% positives).

**Examples:** crc32fast `CombineZeroLengthIdentity` (only passes when `crc2_init == 0`, probability ~2⁻³²), hex both variants (any non-empty input triggers the bug).

**Behavior:** 80+ regions all tie at Ochiai = 1.0 because every region that fires on any failing input has `ef = N`, `ep = 0`. SBFL has no discriminating signal. The patched region is among those tied at 1.0 — findable but not distinguishable.

**Partial mitigation:** the crabcheck change that snapshots initial-sweep passing inputs would unblock Class C by injecting non-mutation positives into the indices. But for bugs where every *single* random input fails on iteration 0, even that isn't enough.

**Recommendation:** SBFL-on-binary-hits is not useful for this class. Would need either differential coverage (running the property's sub-branches separately) or a smarter value-flow analysis.

## What each pipeline knob bought us

| Change | Who it helps | Evidence |
|---|---|---|
| Drop per-snapshot demangler (inline raw llvm-cov JSON → analysis) | everyone | 20 GB → 3.8 GB/trial, 80 s → 56 s. Rankings identical (last-ULP floats). |
| Rewrite `crabcheck-profiling-fast-analyze` (streaming, no jsondata) | everyone | 56 s → 32 s, 3.8 GB → 230 MB. Same output shape. |
| Env-configurable mutation count | everyone | Lets us do 10 trials at N=100 in the same budget as one N=1000 run. |
| Shrinker in `profiling::quickcheck` | Class B | Rank stabilizes 2-459 → 191. The right line gets identified every run. |
| Subset-tuple Mutate blanket | Class B | Mutation fail rate 3.6% → 14.4% on shrunken seeds. Ochiai on cause 0.22 → 0.44. Rank unchanged. |

## Persisted data

```
faultloc-results/
├── REPORT.md                                (this file)
├── README.md                                (quick-start + schema)
├── aho-corasick/
│   ├── replace_all_utf8_safe/
│   │   └── {run1-loose-500iters,run2-tight-1000iters}.json, rankings.md
│   └── find_iter_prefilter_parity/
│       ├── {run1,run2,run3}-*.json, rankings.md
│       ├── matrix/                          (6-config mut×init subsets)
│       │   └── {100,500,1000},{with,without}.json, rankings_matrix.md
│       ├── pooled-20-trials/                (abandoned — disk blowup)
│       └── multi-trial-N100/
│           ├── trials.tsv, trial_{1..10}.json           (no shrink, init=100)
│           ├── trials_noinit.tsv, trial_noinit_*.json   (no shrink, init=0)
│           └── shrink/                      (shrink enabled)
│               ├── trials_shrink.tsv, trial_*.json                  (shrink, N=100)
│               ├── trials_shrink_N1000.tsv, trial_N1000_*.json      (shrink, N=1000)
│               └── trials_shrink_subsetmut_N1000.tsv, trial_subsetmut_*.json
├── crc32fast/
│   └── combine_zero_length_identity/
│       └── run1-tight-1000iters.json, rankings.md
└── ryu/
    └── format32_roundtrip/
        └── multi-trial-N100/
            ├── trials.tsv, trial_{1..10}.json           (10-trial stability)
            └── README.md
```

## What's unsolved

1. **Class B rank ceiling.** Cause functions that fire on every test cannot rank above downstream effects under binary-hit SBFL, regardless of mutation strategy. Fix requires counter-expression-aware analysis (what we called "Plan C" — reads per-region counter deltas across snapshots rather than binary hit/miss).

2. **Class C discrimination.** When 100% of the mutation neighborhood fails, no SBFL formula can distinguish regions. Partial fix: inject positives from the initial random sweep (already implemented, default K=100). Complete fix requires a workload-specific mechanism to reach the positive subspace of the input domain (e.g., biased generators that occasionally return the corner cases where the bug doesn't trigger).

3. **Cause-preserving mutation.** The subset-tuple Mutate improvement is a coarse approximation of what's really needed for Class B: a Mutate that understands which input features the bug depends on (for aho-corasick v2, the superstring prefix relation) and tries to preserve them while perturbing other features. This is workload-specific and not in scope.

4. **Multi-trial pooling.** Attempted pooling 20 aho-corasick v2 trials into one analysis blew past 400 GB disk. Would need Plan C's streaming aggregator to make this tractable. Meanwhile, 10-trial stability stats give most of the value at <1 GB.

## Full 10-trial stability table

All measurements at `N=100 mutations` under the final pipeline (subset-tuple-Mutate blanket, shrink only where a shrinker is defined — currently only `FindIterPrefilterParity`). Each row = 10 RNG-independent runs of `crabcheck-profiling-fast-analyze`.

| Workload / variant | Class | Avg fail rate | Ochiai rank (mode) | Spread | Best region consistently at |
|---|---|---:|---:|---:|---|
| aho-corasick `replace_all_utf8_safe` | A | 78.0% | 2 ×10/10 | 2—2 | `automaton.rs:508` `try_replace_all_with` |
| ryu `format32_roundtrip` | A | ~80% (varies) | 3 ×10/10 | 3—3 | `mod.rs:206` `ryu::pretty::format32` |
| aho-corasick `find_iter_prefilter_parity` (shrink+subset-mut+N=1000) | B | 14.4% | 191 ×8/10 | 191—192 | `noncontiguous.rs:1098` `continue 'PATTERNS;` |
| crc32fast `combine_zero_length_identity` | C | 100% | 75 ×10/10 | 75—75 | `combine.rs:46` `combine::combine` |
| hex `from_hex_accepts_whitespace` | C | 100% | 41 ×10/10 (delta rank 1) | 41—41 | `lib.rs:242` `val` |
| hex `invalid_char_display_raw` | C | 100% (+ ~35% discards) | 76 ×10/10 | 76—76 | `error.rs:38` `InvalidHexCharacter::fmt` |

### Observations

- **Class A (binary signal) and Class C (universal trigger) are perfectly stable across seeds** — every one of 10 trials gives the same rank. The difference is whether that rank is informative (A: rank 2-3, actionable) or not (C: rank 41-76 with 40-75 regions all tied at Ochiai 1.0).
- **Class B was the only unstable class** (2—459 rank spread), and shrink + subset-mut reduced the spread to 191-192 (×8/10 at rank 191). Still doesn't surface the cause above the effect, but the answer is the same every run.
- **hex's `from_hex_accepts_whitespace` is interesting**: it's Class C by failure rate (100%), but **delta ranks the patched `val` function at rank 1** — count-level information captures a signal that binary hit/miss cannot. Ochiai/Tarantula/etc. are stuck at rank 41 because every failing snapshot hits the `val` region (so ef=101, ep=0, Ochiai=1.0, tied with ~40 other regions).
- **ryu's Tarantula is notably unstable** (same behavior as on aho-corasick v1): 4, 4, 36, 2, 9, 7, 35, 29, 20, 2. All other metrics are rank 3 ×10/10. The tie-breaking in Tarantula's "ratio of failing ratios" formula is sensitive to which regions happen to have `ef > 0, ep = 0` by RNG.
- **Where delta outperforms SBFL**: specifically hex v1 (rank 1 by delta, rank 41 by Ochiai). Whenever a bug manifests as a *count difference* in an always-hit region, delta is the right metric; binary-hit SBFL is tied at 1.0.

### Stability ≠ usefulness

The final tally:

| Class | Example | Rank stable? | Top-K actionable? |
|---|---|---|---|
| A | ryu, aho-corasick v1 | ✅ | ✅ |
| B | aho-corasick v2 | ✅ (after shrink) | ⚠️ wrong function at top, right LINE within function |
| C (cause counted differently than noise) | hex v1 | ✅ | ✅ via delta (not SBFL) |
| C (pure binary-hit) | crc32fast, hex v2 | ✅ | ❌ all metrics tied |

Stability was the first-order property to fix (and we did). Usefulness depends on bug class and whether a count-aware signal like delta is checked. For benchmarking purposes, the pipeline produces clean reproducible data — good ground-truth evaluation input.

## Stopping points

The pipeline is production-quality for Class A bugs. Class B bugs have a robust "reproducibly-identifies-the-right-line-in-its-file" behavior. Class C bugs split into two: count-distinguishable ones (delta rank 1, hex v1) and pure-hit ones (everything tied, crc32fast, hex v2) — the latter is a research problem, not a pipeline gap.
