# fast-float2 — 1 variant

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| decimal_trailing_zeros | 24/77 | A | `fast_float::binary::compute_float::<f64>` binary.rs:43 (ochiai 0.97, Δ=0.79) |

The `DecimalShape` generator biases 3/4 toward mantissa in `9_007_199_254_740_992..=9_007_199_254_741_200` (exactly at the 2^53 f64 precision boundary) with `tz` in `800..=1500` — this is the region where the trailing-zeros rounding bug fires. **Without the bias, random u64 mantissas almost never land in the trigger window.**

Top ochiai surfaces `compute_float::<f64>` — the precision-sensitive decimal-to-binary conversion path.

Generator: `DecimalShape { mantissa: u64, tz: u16 }` with bit-flip Mutate — copied from `src/bin/etna.rs` DecimalShape.
