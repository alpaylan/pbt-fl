# half — 3 variants

| Variant | Pos/Neg | Class | Top region (best metric) |
|---|---|---|---|
| max_min_nan_handling | 11/91 | A | `f16::to_bits` at binary16.rs:119-121 (Ochiai 0.94) |
| partial_cmp_sign_magnitude | 6/95 | **D (silent-value)** | only property's Fail arm has delta>0; the bug changes returned `Ordering` but doesn't change which code is executed |
| subnormal_conversion | 0/67 (91 disc) | C | `leading_zeros_u16` (Ochiai 1.0 tied) |

partial_cmp_sign_magnitude joins itertools/merge_join_size_hint_overflow as the second confirmed Class D bug — both flip return values without changing control flow.
