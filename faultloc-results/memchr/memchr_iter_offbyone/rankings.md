# memchr `MemchrIterMatchesNaive` (single-trial validation)

- Patch: `patches/memchr_iter_offbyone_8313aeb_1.patch` — `Memchr::next` post-shifts every match index by `+1`
- Ground truth: `<Memchr as Iterator>::next` @ `src/memchr.rs:338`
- Mutation config: `CRABCHECK_PROFILING_MUTATIONS=100`

Single trial: pos=4, neg=97 (~96% fail rate). 5979 regions total.

| Metric | Rank of src/memchr.rs region | Score | Line |
|---|---:|---:|---:|
| ochiai | 8 | 1.0 | 338 |
| tarantula | 8 | 1.0 | 338 |
| dstar | 8 | 1.8e308 | 338 |
| jaccard | 8 | 1.0 | 338 |
| op2 | 8 | 97.0 | 338 |
| delta | 23 | 2.77 | 533 |

Class A-ish: SBFL metrics put the patched function (Memchr::next) at rank 8, behind 7 regions in memchr::vector::aarch64neon (SIMD move-mask path that runs heavily on matching haystacks).

Top 3 non-property regions by Ochiai:
- `vector.rs:443` `NeonMoveMask::…` — SIMD match-mask register read
- `vector.rs:442` `NeonMoveMask::…`
- `vector.rs:442` `NeonMoveMask::…`
