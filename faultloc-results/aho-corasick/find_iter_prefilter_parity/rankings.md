# aho-corasick `FindIterPrefilterParity`

## Metadata

- Crate: `aho-corasick` (workloads/Rust/aho-corasick)
- Property fn: `aho_corasick::etna::property_find_iter_prefilter_parity`
- Injection kind: patch (`patches/prefilter_pattern_id_sync_2df0983_1.patch`)
- Ground truth: `Compiler::build_trie` @ `src/nfa/noncontiguous.rs` (patched lines ~1132-1136 and removed block at original lines 1082-1094)
- Bug semantics: moves the `prefilter.add(pat)` call to *after* the pattern walk, so patterns short-circuited by leftmost-first prefix matching never register with the prefilter; downstream `find_iter` reports wrong `PatternID`s when the prefilter is on.

**Note on rank position:** this variant exemplifies the 'cause runs equally on pass and fail, effect diverges' class of bug. SBFL metrics rank the downstream prefilter path (`packed::rabinkarp::RabinKarp::verify/find_at`) above the actual patched function.

## run1-loose-500iters

Mutate mode: aggressive (add/insert/remove/replace, 500 mutation iterations).
  - positive_samples: **217**
  - negative_samples: **284**
  - total_regions: 9296  (delta>0: 1202)

**Ground-truth rank by each metric** (sorted descending; ties broken by SBFL input order):

| Metric | Rank | Score |
| --- | ---: | ---: |
| ochiai | 272 | 0.77568996 |
| tarantula | 288 | 0.53580246 |
| dstar | 272 | 429.021276 |
| jaccard | 273 | 0.60169491 |
| op2 | 245 | 283.137614 |
| delta | 186 | 2.50292075 |

**Top-10 non-property regions by Ochiai:**

| Ochiai | File:Line | Function |
| ---: | --- | --- |
| 0.9290 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.9290 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.9290 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.9290 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.9290 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.9290 | `rabinkarp.rs:102` | `<aho_corasick::packed::rabinkarp::RabinKarp>::find_at` |
| 0.9290 | `rabinkarp.rs:101` | `<aho_corasick::packed::rabinkarp::RabinKarp>::find_at` |
| 0.9290 | `pattern.rs:223` | `<aho_corasick::packed::pattern::Pattern>::len` |
| 0.9290 | `pattern.rs:222` | `<aho_corasick::packed::pattern::Pattern>::len` |
| 0.9290 | `pattern.rs:222` | `<aho_corasick::packed::pattern::Pattern>::len` |

**Top-10 non-property regions by raw delta:**

| Δ | pos_avg | neg_avg | File:Line | Function |
| ---: | ---: | ---: | --- | --- |
| 236.8085 | 27770. | 28007. | `primitives.rs:171` | `<aho_corasick::util::primitives::SmallIndex>::as_usize` |
| 236.8085 | 27770. | 28007. | `primitives.rs:170` | `<aho_corasick::util::primitives::SmallIndex>::as_usize` |
| 236.8085 | 27770. | 28007. | `primitives.rs:168` | `<aho_corasick::util::primitives::SmallIndex>::as_usize` |
| 230.2098 | 25886. | 26117. | `primitives.rs:453` | `<aho_corasick::util::primitives::StateID>::as_usize` |
| 230.2098 | 25886. | 26117. | `primitives.rs:452` | `<aho_corasick::util::primitives::StateID>::as_usize` |
| 230.2098 | 25886. | 26117. | `primitives.rs:452` | `<aho_corasick::util::primitives::StateID>::as_usize` |
| 230.2098 | 25886. | 26117. | `primitives.rs:451` | `<aho_corasick::util::primitives::StateID>::as_usize` |
| 116.8696 | 13244. | 13361. | `alphabet.rs:39` | `<aho_corasick::util::alphabet::ByteClasses>::get` |
| 116.8696 | 13244. | 13361. | `alphabet.rs:38` | `<aho_corasick::util::alphabet::ByteClasses>::get` |
| 116.8696 | 13244. | 13361. | `alphabet.rs:37` | `<aho_corasick::util::alphabet::ByteClasses>::get` |

## run2-tight-1000iters

Mutate mode: single-point perturbation (one byte/char replaced per call, 1000 mutation iterations). Pass rate **increased** to 74% — tight mutations more often break the superstring-prefix relation that triggers the short-circuit, so they escape the bug.
  - positive_samples: **741**
  - negative_samples: **260**
  - total_regions: 9296  (delta>0: 554)

**Ground-truth rank by each metric** (sorted descending; ties broken by SBFL input order):

| Metric | Rank | Score |
| --- | ---: | ---: |
| ochiai | 206 | 0.62955656 |
| tarantula | 211 | 0.65171503 |
| dstar | 206 | 170.707070 |
| jaccard | 206 | 0.39634146 |
| op2 | 206 | 259.466307 |
| delta | 34 | 2.88947368 |

**Top-10 non-property regions by Ochiai:**

| Ochiai | File:Line | Function |
| ---: | --- | --- |
| 0.7414 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.7414 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.7414 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.7414 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.7414 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.7414 | `rabinkarp.rs:102` | `<aho_corasick::packed::rabinkarp::RabinKarp>::find_at` |
| 0.7414 | `rabinkarp.rs:101` | `<aho_corasick::packed::rabinkarp::RabinKarp>::find_at` |
| 0.7414 | `pattern.rs:223` | `<aho_corasick::packed::pattern::Pattern>::len` |
| 0.7414 | `pattern.rs:222` | `<aho_corasick::packed::pattern::Pattern>::len` |
| 0.7414 | `pattern.rs:222` | `<aho_corasick::packed::pattern::Pattern>::len` |

**Top-10 non-property regions by raw delta:**

| Δ | pos_avg | neg_avg | File:Line | Function |
| ---: | ---: | ---: | --- | --- |
| 41.76842 | 444.63 | 486.4 | `prefilter.rs:551` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 41.76842 | 444.63 | 486.4 | `prefilter.rs:551` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 41.76842 | 444.63 | 486.4 | `prefilter.rs:551` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 41.76842 | 444.63 | 486.4 | `prefilter.rs:550` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 41.23576 | 442.46 | 483.7 | `prefilter.rs:554` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 39.11862 | 974.78 | 1013.9 | `alphabet.rs:284` | `<aho_corasick::util::alphabet::ByteSet>::contains` |
| 39.11862 | 974.78 | 1013.9 | `alphabet.rs:283` | `<aho_corasick::util::alphabet::ByteSet>::contains` |
| 39.11862 | 974.78 | 1013.9 | `alphabet.rs:282` | `<aho_corasick::util::alphabet::ByteSet>::contains` |
| 39.11862 | 974.78 | 1013.9 | `alphabet.rs:282` | `<aho_corasick::util::alphabet::ByteSet>::contains` |
| 39.11862 | 974.78 | 1013.9 | `alphabet.rs:281` | `<aho_corasick::util::alphabet::ByteSet>::contains` |

## run3-tight-1000iters-initial-passes

Same as run2 *plus* the crabcheck patch at `crabcheck/src/profiling.rs:62-78` that snapshots up to 100 passing iterations from the outer 0..20000 random sweep and includes them in the positives list. **The intent was to give SBFL a more diverse positive set** — random inputs vs. mutation-derived ones that all live in the failing seed's neighborhood. This trial captured 16 initial-sweep positives among 604 total positives.

  - positive_samples: **604**
  - negative_samples: **413**
  - total_regions: 9296  (delta>0: 594)

**Ground-truth rank by each metric** (sorted descending; ties broken by SBFL input order):

| Metric | Rank | Score |
| --- | ---: | ---: |
| ochiai | 385 | 0.63725690 |
| tarantula | 403 | 0.5 |
| dstar | 385 | 282.399006 |
| jaccard | 385 | 0.40609636 |
| op2 | 380 | 412.001652 |
| delta | 22 | 4.20787967 |

**Top-10 non-property regions by Ochiai:**

| Ochiai | File:Line | Function |
| ---: | --- | --- |
| 0.8155 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.8155 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.8155 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.8155 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.8155 | `rabinkarp.rs:143` | `<aho_corasick::packed::rabinkarp::RabinKarp>::verify` |
| 0.8155 | `rabinkarp.rs:102` | `<aho_corasick::packed::rabinkarp::RabinKarp>::find_at` |
| 0.8155 | `rabinkarp.rs:101` | `<aho_corasick::packed::rabinkarp::RabinKarp>::find_at` |
| 0.8155 | `pattern.rs:223` | `<aho_corasick::packed::pattern::Pattern>::len` |
| 0.8155 | `pattern.rs:222` | `<aho_corasick::packed::pattern::Pattern>::len` |
| 0.8155 | `pattern.rs:222` | `<aho_corasick::packed::pattern::Pattern>::len` |

**Top-10 non-property regions by raw delta:**

| Δ | pos_avg | neg_avg | File:Line | Function |
| ---: | ---: | ---: | --- | --- |
| 38.56953 | 473.43 | 512.0 | `prefilter.rs:551` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 38.56953 | 473.43 | 512.0 | `prefilter.rs:551` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 38.56953 | 473.43 | 512.0 | `prefilter.rs:551` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 38.56953 | 473.43 | 512.0 | `prefilter.rs:550` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 38.02483 | 470.97 | 509.0 | `prefilter.rs:554` | `<aho_corasick::util::prefilter::RareBytesBuilder>::build::imp` |
| 36.09938 | 1008.5 | 1044.6 | `alphabet.rs:284` | `<aho_corasick::util::alphabet::ByteSet>::contains` |
| 36.09938 | 1008.5 | 1044.6 | `alphabet.rs:283` | `<aho_corasick::util::alphabet::ByteSet>::contains` |
| 36.09938 | 1008.5 | 1044.6 | `alphabet.rs:282` | `<aho_corasick::util::alphabet::ByteSet>::contains` |
| 36.09938 | 1008.5 | 1044.6 | `alphabet.rs:282` | `<aho_corasick::util::alphabet::ByteSet>::contains` |
| 36.09938 | 1008.5 | 1044.6 | `alphabet.rs:281` | `<aho_corasick::util::alphabet::ByteSet>::contains` |

**Effect of the change:**

| Metric | run2 rank | run3 rank | Δ |
| --- | ---: | ---: | :---: |
| ochiai | 206 | 385 | worse |
| tarantula | 211 | 403 | worse |
| dstar | 206 | 385 | worse |
| jaccard | 206 | 385 | worse |
| op2 | 206 | 380 | worse |
| delta | 34  | 22  | **better** |

The 16 random positives mostly hit `build_trie` (every test compiles the automaton), so its binary hit/no-hit ratio between pos and neg moves *toward* parity, which Ochiai/Tarantula/etc. read as *less* suspicious. Raw delta benefits because random positives exercise larger pattern sets — the per-snapshot execution count of `build_trie`'s inner loop diverges more sharply between random pos and clustered neg (Δ went 2.89 → 4.21).

Conclusion: the crabcheck-level fix is real but on the wrong axis for this bug class. SBFL needs *fewer* positives that don't hit the cause function, not *more* that do.
