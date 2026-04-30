# simdutf8 — 2 variants (rich mixed samples)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| incomplete_eof_basic | 71/30 | A | `SimdU8Value::from_32_cut_off_leading` aarch64/neon.rs:52 (ochiai 0.67, Δ=0.24) |
| incomplete_eof_compat | 70/31 | A | `validate_utf8_compat_simd0` algorithm.rs:308 (ochiai 0.71, Δ=0.56) |

Both marauders-kind variants produce strong mixed distributions. The `BiasedBytes` generator mirrors the existing crabcheck adapter: 3/4 chance of building a 64/128/192-byte buffer with a trailing 0xC0..=0xFF continuation byte landing right on a SIMD chunk boundary — this exact shape is what the incomplete-EOF bug needs. **Reinventing with plain random bytes would miss the bug slice entirely.**

Top regions point at the SIMD neon/aarch64 path — the architecture-specific incomplete-handling branch.
