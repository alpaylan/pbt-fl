# bitvec-rs — 6 variants (all Class B)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| split_at_mut_rejects_len | 0/101 | B | `Cell<usize>::fetch_or` (radium 0.7.0) lib.rs:564 (ochiai 1.0, Δ=17.2) |
| vec_insert_rejects_end | 0/101 | B | `Cell<usize>::fetch_or` lib.rs:564 (Δ=5.8) |
| leading_trailing_homogeneous | 0/101 | B | `NonNull::new` via `tap::Pipe::pipe` pipe.rs:73 (Δ=8.9) |
| bitvec_partial_cmp_reversed | 0/101 | B | `Cell<usize>::fetch_or` lib.rs:564 (Δ=11.3) |
| clone_from_bitslice_src_bug | 0/101 | B | `Cell<u8>::fetch_and` lib.rs:554 (Δ=5.0) |
| octal_fmt_buffer_size | 0/101 | B | `Cell<u64>::fetch_or` lib.rs:564 (Δ=39.0) |

All six variants fire on the first random bitvec input — the bug-triggering input space for each is large (any bit vector with the right length or any value pair with ordering disparity). SBFL ties at 1.0 across the failure-path regions; delta discriminates.

Recurring signal: `radium::Radium` cell-ops (`fetch_or`, `fetch_and`) appear near the top across 4 of 6 variants — these are bitvec's low-level bit-manipulation primitives that are invoked on every buggy path. Plus `tap::Pipe::pipe` wrapping `NonNull::new` for the pointer-building path used by `leading_trailing`.

Generator: `Bits` = `Vec<bool>` length 0..32 — copied verbatim from `src/bin/etna.rs` `Bits` wrapper.
