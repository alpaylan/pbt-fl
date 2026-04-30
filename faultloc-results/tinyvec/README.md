# tinyvec — 4 variants (all marauders)

Summary table (single-trial, N=100):

| Variant | Pos/Neg | Top Ochiai region | Top delta region |
|---|---|---|---|
| debug_alternate_empty | 0/101 | `arrayvec.rs:1864-1867` **Debug::fmt** (patched fn) | `const_generic_impl.rs:19` Array::default (Δ=8) |
| remove_past_end_silent | 0/76 (25 disc) | `arrayvec.rs:846-850` **ArrayVec::remove** (patched fn) | `const_generic_impl.rs:19` (Δ=8) |
| swap_remove_last | 0/101 | `arrayvec.rs:1187-1190` **ArrayVec::swap_remove** (patched fn) | same |
| drain_end_off_by_one | 3/100 | `arrayvec.rs:797-799` try_push (Ochiai 0.985) | `try_push` (Δ=1.32) |

**Three of four variants (variants 1-3) have the patched function as top-Ochiai region.** Unusual and clean — the marauders mutations directly change `ArrayVec::{remove, swap_remove, Debug::fmt}` bodies, so the bug-affected region IS the patched region. Unlike smallvec where the effect propagated to a helper, tinyvec's debug/remove/swap_remove mutations manifest in-place.

Drain is Class A-ish (try_push fires more on failing), same pattern as aho-corasick v1.
