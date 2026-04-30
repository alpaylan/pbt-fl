# im-rs — 6 variants (all trigger)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| path_next_backtrack | 0/101 | B | `sized_chunks::Chunk::new` sized_chunk/mod.rs:148 (ochiai 1.0, Δ=634) |
| range_off_by_one | 3/93 | A | `sized_chunks::Chunk::Drop::drop` sized_chunk/mod.rs:116 (ochiai 0.98, Δ=-4.85) |
| rrb_debug_pop | 0/101 | B | `sized_chunks::InlineArray::len_const` inline_array/mod.rs:160 (ochiai 1.0, Δ=39) |
| rrb_density_check | 0/101 | B | `InlineArray::len_const` inline_array/mod.rs:160 (same as rrb_debug_pop — shared hot path) |
| ptr_eq_precedence | 5/96 | A | `InlineArray::len_const` inline_array/mod.rs:154 (ochiai 0.97) |
| eq_single_chunk | 0/101 | B | `InlineArray::len_const` inline_array/mod.rs:160 (ochiai 1.0, Δ=78) |

Five of six variants fire on every random seed (Class B); `range_off_by_one` and `ptr_eq_precedence` produce enough passing inputs for SBFL discrimination.

The im-rs `sized_chunks` crate is the RRB (Relaxed Radix Balanced) tree's internal storage — virtually every im-rs code path goes through `Chunk` or `InlineArray`, so their hot-path regions appear at the top of every variant's ranking. This is a known property of data-structure libraries: the "bug-indicator helper" is the underlying storage layer, not the specific fixed function.

Generators: seeded `u32` derivations (multiplicative mixing from the `usize` input), mirroring the existing `cc_*_seeded` closures in `src/bin/etna.rs`. For `EqSingleChunk`, the seed expands to a `Vec<i32>` via linear congruential generation — required to reach the RRB "single chunk" branch at consistent sizes.
