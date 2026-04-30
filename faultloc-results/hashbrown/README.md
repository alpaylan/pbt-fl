# hashbrown — 1 variant

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| rehash_panic_length | 0/101 | B | `allocator_api2::Global::alloc_impl` (ochiai 1.0) |

The property makes a table, then triggers a rehash with a panic injection at a specific count. Every random `panic_count_byte` triggers the panic under the variant — top ochiai ties at 1.0 and points at the hashbrown allocator path.

Generator: `panic_count_byte: usize` cast to `u8` — matches `src/bin/etna.rs RehashPanicInput` (`u8` alone).
