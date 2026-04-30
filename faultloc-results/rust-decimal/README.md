# rust-decimal — 6 of 8 variants triggered

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| abs_sub_returns_abs | 37/65 | A | `ArrayString::<32>::capacity` arrayvec/array_string.rs:166 (ochiai 1.0, Δ=15.6) |
| is_integer_scale_decrement | n/a | — | **not triggered** — bug requires scale > 9 at rescale time with specific num values; `(i32, usize)` with size-scaled ranges rarely reaches the buggy arithmetic branch |
| from_i128_negation_overflow | 84/17 | A | `Decimal::from_i128` decimal.rs:2055 (ochiai 0.41) |
| round_dp_early_return_reorder | 62/47 | A | `ArrayString::<32>::capacity` (ochiai 1.0, Δ=20.7) |
| checked_ln_zero_panic | n/a | — | **not triggered** — `d.checked_ln()` routes through upper-layer zero-check before reaching the mutated `ln_wide`; removing the `is_zero` guard in `ln_wide` alone isn't reachable for the test inputs |
| scientific_fmt_zero | 64/37 | A | `ArrayString::<32>::capacity` (ochiai 1.0, Δ=6.1) |
| scientific_scale_overflow | 88/30 | A | `Decimal::from_scientific_exact` decimal.rs:580 (ochiai 0.63, Δ=0.49) |
| div_remainder_overflow | 31/70 | A | `ArrayString::<32>::capacity` (ochiai 1.0, Δ=51.0) |

Six of eight variants produce strong mixed distributions. Recurring signal: `ArrayString::<32>::capacity` (the Decimal-to-string buffer) dominates four variants — all involve conversion paths that stringify the decimal.

**4/5-argument properties** use nested tuples to stay within crabcheck's 3-ary Mutate: `AbsSubDifference(i64, u32, i64, u32)` → `(i32, (usize, i32, usize))`, `CheckedDivNoPanic(i64, u8, i64, u8, u8)` → `((i32, usize, i32), (usize, usize))`.

Two variants don't trigger under the default generators:
- `is_integer_scale_decrement` needs scale > 9 when the rescale loop runs, which is hard to hit with size-scaled `usize`.
- `checked_ln_zero_panic` needs to reach `ln_wide(Decimal::ZERO)` but upper-layer guards short-circuit before the mutated function runs.

Both could likely be recovered with a pool-biased generator that surfaces `(num=0, scale=0)` and `(num=*, scale=10..=20)` corners explicitly.
