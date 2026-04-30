# rangemap — 4 variants (all trigger after perturb-based generator fix)

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| coalesce_contiguous | 14/92 | A | std_ext.rs:23 Range::overlaps (0.94) / map.rs:493 adjust_touching_ranges (Δ=0.37) |
| partialeq_map | 91/13 | A | map.rs:141-142 RangeMap::len (1.0) / range_wrapper.rs:52-54 RangeStartWrapper::PartialOrd (Δ=4.05) |
| inclusive_equality | 183/18 | B | inclusive_map.rs:234 PartialEq impl (1.0) — patched fn |
| overlapping_backwards | 0/101 | C-count | std_ext.rs:23 Range::overlaps (1.0) / range_wrapper.rs:142 RangeEndWrapper::PartialOrd (**Δ=84.94**) |

Generator fix: `TwoInserts::generate` uses `perturb_triples(a, rng)` to derive `b` from `a` (one-slot perturbation), mirroring the existing crabcheck adapter's `perturb_inserts_cc`. Independent random `a, b` pairs almost never compare-as-equal-but-aren't, which is the exact condition the partialeq bug needs.
