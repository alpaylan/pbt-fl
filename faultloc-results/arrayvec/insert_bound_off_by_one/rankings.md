# arrayvec `InsertAtLengthSucceeds` (single-trial)
- Marauders: `insert_bound_off_by_one_2a1378d_1` — off-by-one in `insert` bounds check.
- pos=0, neg=101 (100% fail, Class C-count)
- Ochiai: tied at 1.0 across many regions, top is `ArrayVec::get` at arrayvec_impl.rs:81
- **Delta: rank 1 at Δ=15.84, `ArrayVec::len` at arrayvec.rs:114** — strongest signal: the len accessor is called 15.8× more on failing snapshots (off-by-one causes extra boundary checks per iteration).
