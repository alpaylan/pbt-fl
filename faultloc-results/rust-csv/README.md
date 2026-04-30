# rust-csv — 7 variants (all trigger)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| core_reader_reset_output_pos_zero | 0/101 | B | `csv_core::Reader::default` reader.rs:132 (ochiai 1.0) |
| reader_trim_all_without_headers | 0/83 | B | `csv_core::Reader::default` reader.rs:132 (ochiai 1.0) |
| writer_comment_char_auto_quote | 0/101 | B | `csv_core::Reader::default` reader.rs:132 (ochiai 1.0) |
| byte_record_eq_field_boundaries | 172/28 | A | `csv::etna::split_bytes` etna.rs:236 (ochiai 0.40, Δ=2.25) |
| byte_record_eq_length_check | 117/26 | A | `split_bytes::closure#1` etna.rs:230 (ochiai 0.48) |
| core_reader_comment_only_at_record_start | 0/101 | B | `csv_core::Reader::default` reader.rs:132 (ochiai 1.0) |
| deserialize_byte_buf_bypasses_utf8 | 0/101 | B | `Vec<u8>::deserialize` serde_bytes/de.rs:53 (ochiai 1.0) |

Two `ByteRecordEq*` variants share the same property (`ByteRecordEqMatchesFields`) and test different aspects of the eq invariant — both produce rich mixed samples; SBFL correctly points at `split_bytes` (the fields extractor used in the comparison).

The other five variants fire on every random CSV input (Class B). Recurring signal: `csv_core::Reader::default` — the reader constructor is touched on every code path the tests exercise, so it naturally dominates the ochiai tie.

Generators: `Bytes24` / `Splits5` / `ByteFields` with newtype wrappers and explicit Mutate — mirrors `src/bin/etna.rs` verbatim. The 4-ary `ByteRecordEqMatchesFields` property uses a nested `(Bytes24, (Splits5, Splits5, usize))` tuple because crabcheck's Mutate only covers up to 3-ary.
