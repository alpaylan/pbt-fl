# itertools `KmergeSorted` (single-trial validation)

- Patch: `patches/kmerge_heapify_order_ca70258_1.patch` — flips `heapify`'s internal-node loop from `(0..n/2).rev()` (bottom-up, correct) to `0..n/2` (forward, produces invalid heap)
- Ground truth: `kmerge_impl::heapify` → `kmerge_impl::sift_down` @ `src/kmerge_impl.rs:~88-100`
- Config: `CRABCHECK_PROFILING_MUTATIONS=100`

Single trial: pos=5, neg=99 (**95% fail rate**). 9648 regions total.

| Metric | Rank | Score | Line / fn |
|---|---:|---:|---|
| **ochiai** | **2** | 0.985 | kmerge_impl.rs:97 sift_down |
| **tarantula** | 2 | 0.625 | kmerge_impl.rs:97 sift_down |
| **dstar** | 2 | 3267 | kmerge_impl.rs:97 sift_down |
| **jaccard** | 2 | 0.971 | kmerge_impl.rs:97 sift_down |
| **op2** | 2 | 98.5 | kmerge_impl.rs:97 sift_down |
| **delta** | **1** | 1.60 | kmerge_impl.rs:189 kmerge_by |

Top 5 non-property regions by Ochiai are all in `kmerge_impl.rs` — sift_down's child-max-index comparison at lines 95-97 (ef=99, ep=3). Clean Class A bug: the buggy `heapify` creates an invalid heap, which causes `sift_down` to fire with a different access pattern on failing runs.

Delta picks up a different piece (`kmerge_by` entry at line 189) as rank 1 — count-level signal from the extra heap-rebuild work.
