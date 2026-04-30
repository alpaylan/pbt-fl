# aho-corasick `ReplaceAllUtf8Safe`

## Metadata

- Crate: `aho-corasick` (workloads/Rust/aho-corasick)
- Property fn: `aho_corasick::etna::property_replace_all_utf8_safe`
- Injection kind: patch (`patches/replace_all_utf8_boundary_e453f60_1.patch`)
- Ground truth: `try_replace_all_with` @ `src/automaton.rs:508`
- Bug semantics: removes the `is_char_boundary` guard in `try_replace_all_with`; `replace_all` panics when a byte-level match splits a multi-byte UTF-8 scalar.

## run1-loose-500iters

Mutate mode: aggressive (add/insert/remove/replace, 500 mutation iterations).
  - positive_samples: **81**
  - negative_samples: **420**
  - total_regions: 9288  (delta>0: 438)

**Ground-truth rank by each metric** (sorted descending; ties broken by SBFL input order):

| Metric | Rank | Score |
| --- | ---: | ---: |
| ochiai | 2 | 1.0 |
| tarantula | 23 | 1.0 |
| dstar | 2 | 1.79769313 |
| jaccard | 2 | 1.0 |
| op2 | 2 | 420.0 |
| delta | 33 | 1.0 |

**Top-10 non-property regions by Ochiai:**

| Ochiai | File:Line | Function |
| ---: | --- | --- |
| 1.0 | `automaton.rs:508` | `<alloc::sync::Arc<dyn aho_corasick::ahocorasick::AcAutomaton> as aho_c` |
| 0.9941 | `search.rs:691` | `<aho_corasick::util::search::Span>::is_empty` |
| 0.9941 | `search.rs:690` | `<aho_corasick::util::search::Span>::is_empty` |
| 0.9941 | `search.rs:689` | `<aho_corasick::util::search::Span>::is_empty` |
| 0.9941 | `search.rs:922` | `<aho_corasick::util::search::Match>::start` |
| 0.9941 | `search.rs:921` | `<aho_corasick::util::search::Match>::start` |
| 0.9941 | `search.rs:920` | `<aho_corasick::util::search::Match>::start` |
| 0.9941 | `search.rs:944` | `<aho_corasick::util::search::Match>::span` |
| 0.9941 | `search.rs:943` | `<aho_corasick::util::search::Match>::span` |
| 0.9941 | `search.rs:942` | `<aho_corasick::util::search::Match>::span` |

**Top-10 non-property regions by raw delta:**

| Δ | pos_avg | neg_avg | File:Line | Function |
| ---: | ---: | ---: | --- | --- |
| 34.43994 | 480.48 | 514.92 | `noncontiguous.rs:371` | `<aho_corasick::nfa::noncontiguous::NFA>::follow_transition_sparse` |
| 34.35017 | 484.39 | 518.74 | `noncontiguous.rs:366` | `<aho_corasick::nfa::noncontiguous::NFA>::follow_transition_sparse` |
| 34.35017 | 484.39 | 518.74 | `noncontiguous.rs:365` | `<aho_corasick::nfa::noncontiguous::NFA>::follow_transition_sparse` |
| 33.78015 | 1257.5 | 1291.3 | `noncontiguous.rs:292` | `<aho_corasick::nfa::noncontiguous::NFA>::iter_trans::{closure#0}` |
| 33.78015 | 1257.5 | 1291.3 | `noncontiguous.rs:291` | `<aho_corasick::nfa::noncontiguous::NFA>::iter_trans::{closure#0}` |
| 33.78015 | 1257.5 | 1291.3 | `noncontiguous.rs:290` | `<aho_corasick::nfa::noncontiguous::NFA>::iter_trans::{closure#0}` |
| 33.78015 | 1257.5 | 1291.3 | `noncontiguous.rs:290` | `<aho_corasick::nfa::noncontiguous::NFA>::iter_trans::{closure#0}` |
| 33.78015 | 1257.5 | 1291.3 | `noncontiguous.rs:289` | `<aho_corasick::nfa::noncontiguous::NFA>::iter_trans::{closure#0}` |
| 32.54664 | 1274.8 | 1307.3 | `noncontiguous.rs:293` | `<aho_corasick::nfa::noncontiguous::NFA>::iter_trans::{closure#0}` |
| 32.54664 | 1274.8 | 1307.3 | `noncontiguous.rs:287` | `<aho_corasick::nfa::noncontiguous::NFA>::iter_trans::{closure#0}` |

## run2-tight-1000iters

Mutate mode: single-point perturbation (one byte/char replaced per call, 1000 mutation iterations).
  - positive_samples: **235**
  - negative_samples: **766**
  - total_regions: 9288  (delta>0: 290)

**Ground-truth rank by each metric** (sorted descending; ties broken by SBFL input order):

| Metric | Rank | Score |
| --- | ---: | ---: |
| ochiai | 2 | 1.0 |
| tarantula | 2 | 1.0 |
| dstar | 2 | 1.79769313 |
| jaccard | 2 | 1.0 |
| op2 | 2 | 766.0 |
| delta | 38 | 1.0 |

**Top-10 non-property regions by Ochiai:**

| Ochiai | File:Line | Function |
| ---: | --- | --- |
| 1.0 | `automaton.rs:508` | `<alloc::sync::Arc<dyn aho_corasick::ahocorasick::AcAutomaton> as aho_c` |
| 0.9815 | `search.rs:691` | `<aho_corasick::util::search::Span>::is_empty` |
| 0.9815 | `search.rs:690` | `<aho_corasick::util::search::Span>::is_empty` |
| 0.9815 | `search.rs:689` | `<aho_corasick::util::search::Span>::is_empty` |
| 0.9815 | `search.rs:922` | `<aho_corasick::util::search::Match>::start` |
| 0.9815 | `search.rs:921` | `<aho_corasick::util::search::Match>::start` |
| 0.9815 | `search.rs:920` | `<aho_corasick::util::search::Match>::start` |
| 0.9815 | `search.rs:944` | `<aho_corasick::util::search::Match>::span` |
| 0.9815 | `search.rs:943` | `<aho_corasick::util::search::Match>::span` |
| 0.9815 | `search.rs:942` | `<aho_corasick::util::search::Match>::span` |

**Top-10 non-property regions by raw delta:**

| Δ | pos_avg | neg_avg | File:Line | Function |
| ---: | ---: | ---: | --- | --- |
| 43.95632 | 1507.6 | 1551.6 | `dfa.rs:833` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:830` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:829` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:829` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:829` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:829` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:828` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:828` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:828` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
| 42.50553 | 1602.2 | 1644.7 | `dfa.rs:827` | `aho_corasick::dfa::sparse_iter::<<aho_corasick::dfa::Builder>::finish_` |
