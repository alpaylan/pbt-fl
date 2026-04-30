# arroy — 3 variants (all trigger)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| bq_len_bits_vs_bytes | 0/101 | B | `property_bq_len_matches_iter` etna.rs:36 (ochiai 1.0) |
| cosine_distance_no_clamp | 32/76 | A | `byteorder::LittleEndian::read_u32` (ochiai 0.84, Δ=1.5) |
| bq_euclid_self_distance_or_not_xor | 0/94 | B | `squared_euclidean_distance_binary_quantized` binary_quantized_euclidean.rs:121 (ochiai 1.0) |

`cosine_distance_no_clamp` needed a special generator: `(Vec<usize>, Vec<usize>, bool)` where the `bool` identical flag forces `a == b` with probability 1/2 so near-parallel vectors (the clamp-bug trigger) are actually sampled. The `usize_vec_to_f32_vec` helper hashes usize → moderate-range f32 because crabcheck has no Mutate for Vec<f32> (f32 doesn't implement Mutate).

Cosine's top ochiai 0.84 points at `byteorder::read_u32` — the binary-quantized vector deserialization path.
