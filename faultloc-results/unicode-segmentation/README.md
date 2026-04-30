# unicode-segmentation — 3 variants

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| grapheme_next_boundary_unwrap | 0/83 | B | `property_grapheme_next_boundary_empty_chunk_no_panic` etna.rs:42-44 (ochiai 1.0) |
| grapheme_prev_boundary_chunk_start | 0/90 | B | `property_grapheme_prev_boundary_chunk_start_no_panic` etna.rs:82 (ochiai 1.0) |
| ascii_word_bound_drop_apostrophe | 26/96 | A | `UWordBounds::next` word.rs:305 (ochiai 0.95, Δ=0.66) |

Two of three fire on every random input (Class B); the ascii word-boundary variant has a rich mixed distribution and SBFL correctly points at `UWordBounds::next` — the iterator whose boundary logic drops the apostrophe.

Generators: `AnyText` = String of 0..16 random Unicode scalar values (via `char::from_u32` rejection), `AsciiText` = String of 0..32 ASCII bytes — copied verbatim from `src/bin/etna.rs`.
