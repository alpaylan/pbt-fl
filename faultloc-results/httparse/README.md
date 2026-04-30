# httparse — 6 variants (all trigger after pool-based generator fix)

| Variant | Pos/Neg | Class | Top region (best metric) |
|---|---|---|---|
| backslash_in_uri | 0/93 | C-count | swar.rs match_uri_vectored (1.0) / iter.rs Bytes::advance (Δ=6.74) |
| chunk_size_overflow | 4/101 | A | **lib.rs:1275-1281 parse_chunk_size (Ochiai 0.985, Δ=8.75)** — exact patched fn |
| header_value_htab | 21/85 | A | lib.rs:1211 parse_headers_iter_uninit (1.0) |
| invalid_token_delim | 0/43 | C-count | swar.rs offsetnz (1.0) / iter.rs Bytes::advance (Δ=10.44) |
| method_leading_space | 6/46 | A | etna.rs:23 is_token_byte (Ochiai 1.0, Δ=1.0) |
| response_no_reason | 35/66 | A | lib.rs:1209-1210 parse_headers_iter_uninit (Ochiai 1.0) / etna.rs:27 is_token_byte (Δ=3.0) |

Generator fix: replaced naive random byte vectors with pool-based generators (METHOD_FIRST_POOL biased toward leading space, HEX_POOL of ASCII hex digits, RESPONSE_TEMPLATES of HTTP-shaped lines) — mirrors existing crabcheck adapter's bias.
