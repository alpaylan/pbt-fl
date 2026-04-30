# buf-list — 1 variant

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| read_exact_pos_on_eof | 1/101 | A (mostly B) | `bytes::Bytes::clone` bytes.rs:532 (ochiai 1.0, Δ=2.85) |

The buggy `Cursor::read_exact` advances `pos` past EOF before detecting the short read, so subsequent reads return the wrong offset. 1 pass (empty chunks) plus 101 failures — just enough positive signal for SBFL.

Top signal is `bytes::Bytes::clone`, invoked on the chunk-access hot path; the fix site lives inside `Cursor::read_exact`.

Generator: `Chunks` = `Vec<Vec<u8>>` outer 0..8 × inner 0..16 random bytes — copied verbatim.
