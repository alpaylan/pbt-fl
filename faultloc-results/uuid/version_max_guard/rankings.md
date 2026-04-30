# uuid `VersionMaxRequiresAllOnes` (single-trial)

- Patch: `version_max_guard_0ed83cf_1.patch` — `get_version` drops the `if self.is_max()` guard, mis-reporting `Version::Max` for any UUID whose version nibble is 0xF.
- Ground truth: `Uuid::get_version` @ `src/lib.rs:594-597`

Single trial: pos=0, neg=101. 33 regions with delta>0. **Class C-count**.

| Metric | Top region | Rank of `get_version` |
|---|---|---:|
| Ochiai (tied at 1.0) | `as_bytes`@803 | **4** (at Ochiai 1.0) |
| Delta | `as_bytes`@803 (Δ=1) then `get_version`@597 (Δ=1) | 4 (tied) |

SBFL puts `get_version` in the top-5 (tied at Ochiai 1.0). The 3 regions ranked higher are all in `as_bytes` — the internal access the property uses to check the byte layout, hit once per test regardless.
