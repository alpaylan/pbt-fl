# uuid `FromToFieldsLeRoundtrip` (single-trial)

- Patch: `to_fields_le_byte_swap_0a096d4_1.patch` — `to_fields_le` computes `d2` using `bytes[5]` twice (should use `bytes[4]` and `bytes[5]`).
- Property: `(d1:u32, d2:u16, d3:u16, d4:[u8;8])` roundtrip through `Uuid::from_fields_le → Uuid::to_fields_le`.
- Ground truth: `Uuid::to_fields_le` @ `src/lib.rs:696-697`

Single trial: pos=0, neg=101 (100% fail). 1827 regions, 69 with delta>0. **Class C-count**.

| Metric | Top region | Rank |
|---|---|---:|
| Ochiai (all tied at 1.0) | `as_bytes`@803, `to_fields_le`@697 | 4 |
| Delta | `as_bytes`@803 (Δ=9) then `to_fields_le`@697 (Δ=1) | 4 |

SBFL finds `to_fields_le` inside the top bucket (Ochiai 1.0 tied with ~50 other regions). Delta surfaces `as_bytes` first (the inner helper that lib.rs:803 calls) because the bug causes byte[5] to be read twice per roundtrip → 9 extra hits per failing trial. The patched `to_fields_le` itself is at rank 4.
