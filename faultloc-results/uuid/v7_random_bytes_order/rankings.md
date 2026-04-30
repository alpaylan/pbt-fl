# uuid `V7EncodeByteLayout` (single-trial)

- Patch: `v7_random_bytes_order_3af4733_1.patch` — `encode_unix_timestamp_millis` swaps `counter_random_bytes[0]` and `[1]` when packing `rand_a`.
- Ground truth: `encode_unix_timestamp_millis` @ `src/timestamp.rs:333-334` (**exact patched region**)

Single trial: pos=0, neg=101. 94 regions with delta>0. **Class C-count — cleanest case**.

| Metric | Top region | Score |
|---|---|---|
| Ochiai (tied at 1.0) | `timestamp.rs:333-334` `encode_unix_timestamp_millis` | 1.0 |
| Delta | same (tied) | 1.0 |

**The top Ochiai regions ARE the patched function** — not a downstream effect, not a wrapper. Top-1 to top-5 all point at the same function. This is the rare Class C case where the patched line happens to also be the only one that fires exactly during the bug's control flow.

Why this time: the bug swaps two inputs to a specific byte-pack instruction. No downstream hot loop amplifies or relays the error; the discrepancy is direct in the output bytes. Unlike hex/crc32fast where the bug propagated into derived data structures.
