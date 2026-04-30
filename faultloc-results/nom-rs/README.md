# nom-rs — 3 variants (all trigger on first random input)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| multispace0_consumes_all_whitespace | 0/101 | B | character/complete.rs:699 `multispace0::{closure#0}` (Δ=10.9) / etna.rs:29 `sanitize_ws` (Δ=10.9) |
| float_parses_infinity_fully | 0/101 | B | branch/mod.rs:41-43 `alt::<recognize_float_or_exceptions::closures>` + error.rs:80 `from_error_kind` (Δ=7.0) |
| count_handles_zero_sized_output | 0/101 | B | etna.rs:126-127 `property_count_handles_zero_sized_output` + `combinator::map` closures |

Every variant's buggy path fires for virtually any non-discarded random input, so all SBFL metrics tie at 1.0. **Delta ranks alone** — and it consistently surfaces the relevant bug helper (`multispace0::closure`, `recognize_float::alt`, `count` parser).

Generator: `Bytes16` with len 0..16 of random bytes + `u8` fallback — same distribution as the existing `src/bin/etna.rs` `Bytes16` wrapper.
