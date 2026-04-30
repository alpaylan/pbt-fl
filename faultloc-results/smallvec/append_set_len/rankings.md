# smallvec `AppendPreservesLength` (single-trial)

- Patch: `append_set_len_1bd2dbc_1.patch` — `SmallVec::append` incorrectly updates the internal length tag after copy, so `a.len() + b.len()` is not preserved.
- Ground truth: `append` / `set_len` / `TaggedLen` machinery in `src/lib.rs`

Single trial: pos=0, neg=101 (**100% fail, Class C-count**). 3253 regions, 256 with delta>0.

| Metric | Top region | Score |
|---|---|---|
| Ochiai (all tied at 1.0) | `SmallVec::drop` @ lib.rs:1988-1990 | 1.0 |
| **Delta** | `TaggedLen::on_heap` @ lib.rs:337-343 | **Δ=12.0** (strongest delta seen in any variant) |

SBFL puts the `Drop` impl at rank 1 because the corrupted state causes dropping to touch different code (heap-reclaim path instead of inline-no-op). Delta directly surfaces `TaggedLen::on_heap` — the tag-check called 12 more times per failing snapshot than per passing one, reflecting the buggy set_len routing through the on-heap path when it shouldn't.

**Delta rank 1 with Δ=12.0 is the strongest signal we've seen** across all workloads.
