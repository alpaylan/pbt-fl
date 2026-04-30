# time — 3 variants

| Variant | Pos/Neg | Class | Top Ochiai | Top delta |
|---|---|---|---|---|
| duration_abs_saturation | 0/73 (28 disc) | C-count | duration.rs:455-456 Duration::new (1.0) — **patched fn** | unsafe_wrapper.rs:24 Unsafe::get (Δ=6) |
| duration_checked_div | 22/59 (36 disc) | A | duration.rs:64-66 Duration::Debug::fmt (1.0) | unsafe_wrapper.rs:24 Unsafe::get (Δ=3) |
| utc_offset_ordering | 41/60 | **A** | **utc_offset.rs:106-107 UtcOffset::Ord::cmp (Ochiai 0.77) — exact patched fn** | same (Δ=1.0) |

UtcOffsetOrdering is a textbook Class A: cleanly localizes to the patched `Ord::cmp` method at the exact lines of the patch.
