# rust-base64 — 2 variants (both trigger)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| binhex_alphabet | 0/101 | C-count | etna.rs:33 binhex_config (Ochiai 1.0) / **alphabet.rs:102 Alphabet::new (Δ=4160)** |
| decoded_len_overflow | 106/2 | C-pure (imbalanced) | no region with delta>0 — bug fires only at exact `usize::MAX` neighbors |

Generator fix: `Usize::generate` now picks from `LEN_POOL = [usize::MAX, MAX-1..MAX-7, MAX/2, ...]` — bias toward overflow-edge values where `decoded_len_estimate` panics.

The Δ=4160 on `Alphabet::new` is the strongest single-region delta in the entire dataset.
