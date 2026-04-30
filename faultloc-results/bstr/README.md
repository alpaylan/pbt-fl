# bstr — 6 variants

| Variant | Pos/Neg | Class | Top Ochiai | Top delta |
|---|---|---|---|---|
| cow_partialeq_self_compare | 0/101 | C-count | utf8.rs:822 decode_step (1.0 tied) | bstr.rs:94-96 BStr::as_bytes (Δ=15.84) |
| debug_control_chars_x1a | 29/30 (136 disc) | A/B | impls.rs:546 BStr::Debug::fmt (1.0) | impls.rs:546 same (Δ=1.0) |
| debug_fffd_not_escaped | 0/101 | C-count | utf8.rs:822 decode_step (tied) | bstr.rs:94-96 BStr::as_bytes (Δ=20.47) |
| debug_hex_uppercase | 0/89 (13 disc) | C-count | utf8.rs:822 decode_step (tied) | bstr.rs:94-96 BStr::as_bytes (Δ=4.0) |
| debug_non_ascii_control | 0/63 (44 disc) | C-count | utf8.rs:683 decode_lossy (tied) | utf8.rs:680-685 (Δ=2.0) |
| splitn_trailing_empty | 40/53 (11 disc) | A | utf8.rs:822 decode_step (tied) | bstr.rs:94-96 BStr::as_bytes (Δ=11.92) |

**Common bug-indicator helpers in bstr**: `bstr::utf8::decode_step` consistently tops Ochiai (UTF-8 decoding is exercised on every test). `BStr::as_bytes` at bstr.rs:94-96 consistently tops delta with strong Δ values across Class C variants. The single Class A variant (debug_control_chars_x1a) has the patched function (`BStr::Debug::fmt`) cleanly at top of both metrics.
