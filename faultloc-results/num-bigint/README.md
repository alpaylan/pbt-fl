# num-bigint — 5 variants (4 mutations, 2 share MulSquareAllOnes property)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| is_multiple_of_zero | 7/95 | A | `biguint::division::div_half` division.rs:78 (ochiai 1.0) |
| mac3_all_zero | 190/11 | A | `BigInt::from_biguint` bigint.rs:585 (ochiai 1.0, Δ=16.0) |
| mul_undersized_buffer | 188/13 | A | `BigInt::Add` bigint/addition.rs:41 (ochiai 1.0, Δ=2.0) |
| neg_isize_promotion | 31/71 | A | `BigInt::Display::fmt` bigint.rs:142 (ochiai 1.0, Δ=2.0) |
| scalar_div_zero | 94/7 | A | `BigUint::is_zero` biguint.rs:156 (ochiai 1.0) |

All five patch-kind variants produce strong mixed distributions — num-bigint's property spaces (random u64 / i64-i16 / u8 bit-shift tags) are broad enough that both passing and failing inputs are sampled.

Note: mac3_all_zero and mul_undersized_buffer share the same property (MulSquareAllOnes), so they're tested by the same generator, producing different ef/ep distributions because the two mutations sit at different mul-algorithm branches.

Generator: bare primitive closures (`|a: usize|`, `|(a, b): (i32, i32)|`) with `as u64`/`as i64`/`as u8` casts inside — matches `src/bin/etna.rs` crabcheck adapter.
