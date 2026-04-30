# slotmap — 4 variants (all trigger)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| kd_debug_null_format | 98/29 | A | `KeyData::default` lib.rs:316 (ochiai 1.0) |
| sparse_secondary_null_insert_guard | 0/101 | B | `property_sparse_secondary_null_insert_ignored` etna.rs:77 (ochiai 1.0) |
| vacant_entry_insert_no_double_count | 0/101 | B | `SlotMap::with_capacity_and_key` basic.rs:223 (ochiai 1.0) |
| slot_clone_from_drops_occupied | 0/101 | B | `Slot::get_mut` basic.rs:58 (ochiai 1.0, Δ=6.2) |

`KdIdx` biases 1/10 toward `u32::MAX` — critical for the `kd_debug_null_format` bug which **only fires when idx == u32::MAX**. The `(KdIdx, u32)` tuple produces enough `u32::MAX` hits to yield a mixed sample.

The other three variants fire on every random input (Class B); top ochiai ties at 1.0 with delta picking out `Slot::get_mut` (for clone_from_drops_occupied) or the property/init helpers.

All 4 variants use `kind = "marauders"` with inline `/*|` markers — applied via `marauders set --variant <id>`, restored from tar backup on exit.
