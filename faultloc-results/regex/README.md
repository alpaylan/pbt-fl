# regex — 3 variants

| Variant | Pos/Neg | Class | Top region |
|---|---|---|---|
| unicode_named_value_negation | 0/101 | B | `regex_automata::hybrid::dfa::DFA::pattern_len` hybrid/dfa.rs:386 (ochiai 1.0, Δ=2.0) |
| captures_get_group_overflow | 94/17 | A | `memchr NEON Finder::with_pair_impl` packedpair.rs:73 (Δ=0.39) |
| alternation_literal_from_alt | 0/101 | B | `regex_syntax::ast::Position::new` ast/mod.rs:427 (ochiai 1.0, Δ=2.0) |

**Generator range fix**: `captures_get_group_overflow` needs `shift ≥ 32` to reach the `index * 2` overflow, but crabcheck's `usize` Arbitrary uses a log2-scaled range (0..=14 in practice). Solved by lifting inside the closure: `let shift = (60 + (shift % 4)) as u8` — targets 60..=63 where the multiplication overflows on 64-bit.

Other two bugs fire on every random input; delta surfaces the matching-path helper in regex-automata/regex-syntax.
