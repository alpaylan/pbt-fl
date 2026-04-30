# smallvec `LeakInlinePanics` (single-trial)

- Patch: `leak_inline_panic_3395246_1.patch` — `SmallVec::leak` returns a `&mut [T]` borrowed from a consumed vector, triggering use-after-move via `TaggedLen` misuse.
- Ground truth: `SmallVec::leak` + `TaggedLen::on_heap` guard in `src/lib.rs`

Single trial: pos=31, neg=80 (72% fail, **Class A/B transitional**). 3247 regions, 301 with delta>0.

| Metric | Top region | Score |
|---|---|---|
| Ochiai | `TaggedLen::value`@346-352 | 0.849 |
| **Delta** | `TaggedLen::on_heap`@337-343 | **Δ=2.66** |

Top non-property regions are all inside `smallvec::TaggedLen<u8>::value` and `::on_heap` at `src/lib.rs:337-352`. These are the length-tag accessors that the buggy `leak` misuses. Signal is moderately strong (Ochiai 0.85, delta 2.66), and the top regions point precisely at the tag-manipulation helpers — rank-1 in both metrics gets you within the right function.
