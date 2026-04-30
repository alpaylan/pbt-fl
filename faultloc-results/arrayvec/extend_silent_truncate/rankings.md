# arrayvec `ExtendPanicsOnOverflow` (single-trial)
- Marauders: `extend_silent_truncate_a554ea2_1` — `.extend()` silently stops at capacity instead of panicking.
- pos=1, neg=101
- Ochiai tied at 1.0.
- **Delta: rank 1 at Δ=5.0, `ArrayVec::extend_from_iter` at arrayvec.rs:1148** — the exact patched function.
