# memchr `MemrchrIterMatchesNaive` (single-trial validation)

- Patch: `patches/memrchr_iter_forward_1b37466_1.patch` — `next_back` dispatches through forward `memchr_raw` instead of reverse `memrchr_raw`
- Ground truth: `Memchr::next_back` in `src/memchr.rs`
- Mutation config: `CRABCHECK_PROFILING_MUTATIONS=100`

Single trial: pos=0, neg=101 (**100% fail rate** — any haystack containing the needle fails the reversal check).

| Metric | Rank of src/memchr.rs region | Score | Line |
|---|---:|---:|---:|
| ochiai | 39 | 1.0 | 533 |
| tarantula | 56 | 1.0 | 533 |
| dstar | 39 | 1.8e308 | 533 |
| jaccard | 39 | 1.0 | 533 |
| op2 | 39 | 101.0 | 533 |
| delta | 60 | 2.0 | 533 |

**Class C-pure**: 0 positives means every hit region ties at Ochiai = 1.0; no discrimination. The tool identifies `memchr_raw` at line 533 (not the actual patched `next_back`) because it's the function the bug routes calls through.

The patched `next_back` itself doesn't appear high because most code that fires is downstream effect (SIMD scan functions), not cause. Same Class C-pure situation as crc32fast: SBFL on binary hits has no signal, would need count-aware analysis or positive-sample injection from a non-mutation source.
