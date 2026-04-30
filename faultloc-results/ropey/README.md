# ropey — 4 variants triggered, 2 require specialized text

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| lines_empty_total_lines | 45/69 | A | smallvec.rs:324-328 `infallible::<()>` (0.78, Δ=-2.0) |
| rope_builder_default_empty_stack | 0/101 | B | smallvec.rs:708-713 `SmallVecData::inline_mut` / `from_inline` (Δ=2.0) |
| rope_hash_chunk_boundary | 0/89 | B | fnv.rs:116-118 `FnvHasher::write` (**Δ=406.9**) |
| utf16_code_unit_conversion | 0/101 | B | smallvec.rs:700-701 `SmallVecData::inline` (Δ=20.0) |
| rope_eq_utf8_boundary | n/a | — | **not triggered in 20k sweep** — witness uses a 1800-char text + specific indices; random generator tops out at 48 chars |
| slice_crlf_split_end_info | n/a | — | **not triggered in 20k sweep** — needs >MAX_BYTES CRLF text with slice end landing inside a CRLF pair |

Four of six variants reach a buggy branch. `lines_empty_total_lines` produces a rich pos/neg mix and lets SBFL discriminate; the other three fire on every input (Class B) so delta alone ranks — but it surfaces the relevant hash/node/chunk-split hot path consistently.

The two "not triggered" variants are highly specialized: the rope-equality bug needs ≥512-byte text crossing an internal-node boundary with a specific 3-byte UTF-8 scalar at the slice end; the CRLF slice bug needs enough content to build an internal-root rope plus a slice endpoint falling exactly between `\r` and `\n`. Neither is reachable from 48-char or 1-32-size-chunk random draws; they'd need either a much larger default-size generator or seeded witness-derived inputs.

Generators: `TextAny`, `TextNonAscii` (1..=48 chars from NON_ASCII pool), `TextChunky` (1..=256), `TextCrlf` (640..=1536 from CRLF_POOL) — all copied verbatim from `src/bin/etna.rs`.
