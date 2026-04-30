# crc32fast `CombineZeroLengthIdentity`

## Metadata

- Crate: `crc32fast` (workloads/Rust/crc32fast)
- Property fn: `crc32fast::etna::property_combine_zero_length_identity`
- Injection kind: marauders (`combine_zero_length_identity_724ceb6_1`, activate with `marauders set --variant combine_zero_length_identity_724ceb6_1`)
- Ground truth: `combine::combine` @ `src/combine.rs` (the early-return `if len2 == 0 { return crc1; }` block is removed; the buggy fall-through reaches `p ^ crc2` at line 45 and returns `crc1 ^ crc2` instead of `crc1`)
- Bug semantics: under the mutant, `combine(crc1, crc2, 0) == crc1 ^ crc2` rather than `crc1`. The property passes iff `crc2_init == 0` — effectively never under random u32 generation, so the mutation neighborhood is monochromatic (0 positives).

**Note: SBFL has no discriminating signal here.** With `positive_samples = 0`, Ochiai = 1.0 for every region hit on every failing iteration (~80+ ties including unrelated init code in `aarch64::State` and `Hasher::finalize`). The ground-truth line's score is tied, not distinguished.

## run1-tight-1000iters

Mutate mode: single bit-flip on one of the two `u32` fields, 1000 mutation iterations. Every mutation reproduces the bug.
  - positive_samples: **0**
  - negative_samples: **1001**
  - total_regions: 287  (delta>0: 81)

**Ground-truth rank by each metric** (sorted descending; ties broken by SBFL input order):

| Metric | Rank | Score |
| --- | ---: | ---: |
| ochiai | 75 | 1.0 |
| tarantula | 75 | 1.0 |
| dstar | 75 | 1.79769313 |
| jaccard | 75 | 1.0 |
| op2 | 75 | 1001.0 |
| delta | 75 | 1.0 |

**Top-10 non-property regions by Ochiai:**

| Ochiai | File:Line | Function |
| ---: | --- | --- |
| 1.0 | `aarch64.rs:29` | `<crc32fast::specialized::aarch64::State>::new` |
| 1.0 | `aarch64.rs:25` | `<crc32fast::specialized::aarch64::State>::new` |
| 1.0 | `aarch64.rs:22` | `<crc32fast::specialized::aarch64::State>::new` |
| 1.0 | `aarch64.rs:21` | `<crc32fast::specialized::aarch64::State>::new` |
| 1.0 | `aarch64.rs:39` | `<crc32fast::specialized::aarch64::State>::finalize` |
| 1.0 | `aarch64.rs:38` | `<crc32fast::specialized::aarch64::State>::finalize` |
| 1.0 | `aarch64.rs:37` | `<crc32fast::specialized::aarch64::State>::finalize` |
| 1.0 | `aarch64.rs:47` | `<crc32fast::specialized::aarch64::State>::combine` |
| 1.0 | `aarch64.rs:46` | `<crc32fast::specialized::aarch64::State>::combine` |
| 1.0 | `aarch64.rs:46` | `<crc32fast::specialized::aarch64::State>::combine` |

**Top-10 non-property regions by raw delta:**

| Δ | pos_avg | neg_avg | File:Line | Function |
| ---: | ---: | ---: | --- | --- |
| 4.0 | 0.0 | 4.0 | `aarch64.rs:39` | `<crc32fast::specialized::aarch64::State>::finalize` |
| 4.0 | 0.0 | 4.0 | `aarch64.rs:38` | `<crc32fast::specialized::aarch64::State>::finalize` |
| 4.0 | 0.0 | 4.0 | `aarch64.rs:37` | `<crc32fast::specialized::aarch64::State>::finalize` |
| 4.0 | 0.0 | 4.0 | `lib.rs:139` | `<crc32fast::Hasher>::finalize` |
| 4.0 | 0.0 | 4.0 | `lib.rs:137` | `<crc32fast::Hasher>::finalize` |
| 4.0 | 0.0 | 4.0 | `lib.rs:137` | `<crc32fast::Hasher>::finalize` |
| 4.0 | 0.0 | 4.0 | `lib.rs:137` | `<crc32fast::Hasher>::finalize` |
| 4.0 | 0.0 | 4.0 | `lib.rs:135` | `<crc32fast::Hasher>::finalize` |
| 4.0 | 0.0 | 4.0 | `lib.rs:134` | `<crc32fast::Hasher>::finalize` |
| 2.0 | 0.0 | 2.0 | `aarch64.rs:29` | `<crc32fast::specialized::aarch64::State>::new` |
