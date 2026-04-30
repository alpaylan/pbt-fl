# encoding_rs — 2 of 3 variants triggered

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| overlong_label_panic | n/a | — | **not triggered in 20k sweep** — bug needs ≥ LONGEST_LABEL_LENGTH (~30) ASCII letters/digits; random u8 bytes hit that alphabet 30/256 per byte, essentially zero probability over a 64-byte input |
| ncr_short_buffer_panic | 3/98 | A | `property_short_buffer_encode_no_panic` etna.rs:71 (ochiai 0.99) |
| encode_utf16_ncr_spill_panic | 9/92 | A | `encoding_rs::ascii::basic_latin_to_ascii` ascii.rs:263 (ochiai 0.98, Δ=1.15) |

Two of three NCR buffer bugs fire with mixed samples — the short-buffer and UTF-16 spill variants are hit by any small output buffer with NCR content.

The overlong-label variant is generator-weak: the bug fires when `trimmed_pos > LONGEST_LABEL_LENGTH` during label parsing, which requires a ≥30-byte run of `[A-Za-z0-9\-_.:]`. Random u8 generators can't reach that distribution reliably — would need a biased ASCII-only generator. Documented as not-triggered; could be fixed with a pool-biased `ForLabelInput` similar to httparse's `METHOD_REST_POOL`.
