# mime — 4 variants (2 via patches, 2 via inline marauders markers)

| Variant | Kind | Pos/Neg | Class | Top region |
|---|---|---|---|---|
| subtype_with_plus | marauders | 0/101 | B | rfc7231.rs:124 `parse::<&str>` (Δ=8.9) / `Atoms::intern` ties at 1.0 ochiai |
| strip_empty_params | marauders | 0/101 | B | `Atoms::intern` / `intern_no_params` ties at 1.0 ochiai (Δ=2.0) |
| ows_before_semicolon | patch | 0/101 | B | rfc7231.rs:319-321 `is_token` (Δ=36.5) / rfc7231.rs:73 `parse` (Δ=13.0) |
| quoted_vs_unquoted_param_eq | patch | 0/101 | B | rfc7231.rs:183-194 `params_from_str` (Δ=13-17) |

All four variants fire on virtually every random input (Class B). All SBFL metrics tie at 1.0 across most covered regions; **delta is the only rank signal**.

The two marauders-kind variants use inline `/*| variant_name */` / `/*|| variant_id */` comment markers at `mime-parse/src/lib.rs:119` and `mime-parse/src/rfc7231.rs:144`. Apply via `marauders set --variant <variant_id>`; back the source file up first and restore from tar after the run because `marauders unset` can fail to parse an already-set file.
