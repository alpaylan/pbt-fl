# indexmap — 1 variant (reverse index off-by-one)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| reverse_indices_offbyone | 1/101 | A (mostly B) | hashbrown raw.rs:534-536 `Bucket::as_ref` (1.0) / bitmask.rs:40 `lowest_set_bit` (Δ=9.0) / raw.rs:918 `RawTable::reserve` (Δ=1.6) |

The mutation reindexes after `IndexMap::reverse()` as `len - i` instead of `len - i - 1`, so any 2+ key map produces out-of-bounds lookups under the variant. 1 passing input survives (the single-slot corner case), 101 failures — SBFL has just enough positive data to differentiate the hashbrown hot path from incidental plumbing.

Top signal is concentrated in `hashbrown::raw::Bucket::as_ref` (the post-reverse lookup path) and `indexmap::inner::equivalent` (the buggy index follows). The actual corrupted index write in `Core::reverse` sits slightly lower in the ranking but is visible via delta.

Generator: `Pairs16` = `Vec<(u16, u16)>` length 0..=16 over keys/values 0..=1024 — mirrors the existing `src/bin/etna.rs` adapter.
