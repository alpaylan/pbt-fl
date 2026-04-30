# smallvec `FromVecZeroCapacity` (single-trial)

- Patch: `from_vec_zero_capacity_944f603_1.patch` — `SmallVec::from_vec` mishandles zero-capacity `Vec`, producing a state that misuses the tagged-length machinery when pushing afterward.
- Ground truth: `from_vec` + `TaggedLen`/`spilled` in `src/lib.rs`

Single trial: pos=0, neg=101 (**100% fail, Class C-count**). 3222 regions, 99 with delta>0.

| Metric | Top region | Score |
|---|---|---|
| Ochiai (tied at 1.0) | `SmallVec::drop` @ lib.rs:1985-1987 | 1.0 |
| **Delta** | `TaggedLen::on_heap` @ lib.rs:337-343 | **Δ=5.0** |

Same pattern as AppendPreservesLength: SBFL ties at 1.0 across 50+ regions with `Drop::drop` appearing first; delta cleanly ranks `TaggedLen::on_heap` at #1 and then `SmallVec::spilled` at #5. Delta's top-5 are all in the tag-machinery — the exact code path corrupted by the buggy `from_vec`.

Across all 3 smallvec variants, **delta consistently surfaces `TaggedLen::on_heap` as the top non-property region** (Δ = 2.66, 12.0, 5.0). That helper is the common indicator of smallvec-tag bugs — essentially the crate's own "assertion point" for the inline/heap distinction, and tag bugs manifest as its hit-count diverging between pass and fail.
