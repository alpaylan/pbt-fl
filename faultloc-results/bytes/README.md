# bytes — 5 variants (all trigger after generator fix)

| Variant | Pos/Neg | Class | Top region (best metric) |
|---|---|---|---|
| chain_remaining_saturating | 1/99 | **D (silent-value)** | only property's Fail arm — saturating_add → wrapping_add no coverage diff |
| get_int_sign_extension | 13/88 | D-like | only 1 delta>0 region |
| get_int_zero_nbytes | 0/101 | C-count | buf_impl.rs:2892 Buf::remaining (Ochiai 1.0 / Δ=2) |
| partialord_bytes_reversed | 0/101 | C-count | bytes.rs:967-990 Bytes::From (1.0 / Δ=1) |
| slice_ref_empty | 0/101 | C-count | bytes.rs:695-697 Bytes::deref (Δ=2) |

Generator fix: `ChainInput::generate` now uses `(a_hi << 32) | a_lo` for full 64-bit usize, mirroring the existing crabcheck adapter — needed to reach the saturating_add overflow regime.
