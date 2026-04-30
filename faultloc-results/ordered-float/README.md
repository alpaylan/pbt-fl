# ordered-float — 4 variants (all trigger with rich positive/negative mix)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| hash_signed_zero | 20/21 | A | `OrderedFloat::hash64` (0.72) + `num_traits::FloatCore::is_nan` (0.72) |
| notnan_binop_skip_nan_check | 66/25 | A | `num_traits::FloatCore::is_nan` macros:9-11 (0.52) / etna `apply_op` at etna.rs:81 (0.52) |
| partial_cmp_delegates_to_inner | 48/56 | A | `num_traits::FloatCore::is_nan` (0.73) — top across ochiai + delta |
| notnan_assign_not_panic_safe | 60/25 | A | `property_assign_panic_safe` etna.rs:154 (1.0) / `FloatCore::is_nan` (0.54) |

All four patch-kind variants produce good mixed-sample distributions because `pick_float`'s 8-value pool (`0.0, -0.0, NaN, INF, -INF, 1.0, -1.0, bit-derived`) straddles the bug-triggering special values. Proper SBFL discrimination — ochiai scores differ by 0.2-0.5 between candidates.

The `is_nan` helpers recurring across variants are a signature of the "NotNan should check NaN on construction" bug family; the property's own `apply_op` / `hash64` / `property_*` helpers appear as always-hit in the failure path.

Generator: bare `(usize, usize)` / `(usize, usize, usize)` tuples with `pick_float(x as u8)` and `pick_op(x as u8)` dispatch — mirrors the existing `src/bin/etna.rs` crabcheck adapter.
