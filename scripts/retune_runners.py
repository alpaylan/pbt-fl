#!/usr/bin/env python3
"""Apply mechanical retuning edits to the 8 overnight workloads' src/bin/etna.rs:

1. Bump framework test counts to ~40M (quickcheck/proptest/hegel).
2. Drop fixed seeds in hegel_settings() so 10 trials diversify.
3. Strip "quickcheck|crabcheck counterexample: " prefixes from the result-match
   arms.
4. Strip the "Property test failed: " wrapper that hegeltest injects around the
   inner panic payload.
5. Add TestError to the proptest imports and switch `.map_err(|e| e.to_string())`
   to a TestError::Fail-aware extraction so the counterexample becomes the
   `reason` string (no proptest boilerplate).

Closure-body surgery (formatting args into the canonical `(a b c)` form) is left
for a per-workload hand-edit because each property's arg types and names vary.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
WORKLOADS = [
    "unicode-segmentation",
    "bitvec-rs",
    "rust-csv",
    "nom-rs",
    "arroy",
    "roaring-rs",
    "regex",
]  # buf-list already done by hand


def find_etna_rs(workload: str) -> Path:
    root = ROOT / "workloads" / "Rust" / workload
    for c in [root / "src/bin/etna.rs", *root.glob("*/src/bin/etna.rs")]:
        if c.exists():
            return c
    raise FileNotFoundError(workload)


REPLACEMENTS: list[tuple[str, str]] = [
    # 1. counts — proptest
    (
        r"TestRunner::new\(ProptestConfig::default\(\)\)",
        "TestRunner::new(ProptestConfig { cases: 40_000_000, ..ProptestConfig::default() })",
    ),
    # roaring-rs already uses `let cfg = ProptestConfig { cases: ..., ..default() }`;
    # bump whatever number is there to 40M. Match the cases assignment line.
    (
        r"cases:\s*\d[\d_]*,",
        "cases: 40_000_000,",
    ),
    # 1. counts — quickcheck
    (
        r"QuickCheck::new\(\)\.tests\(\d[\d_]*\)\.max_tests\(\d[\d_]*\)",
        "QuickCheck::new().tests(40_000_000).max_tests(80_000_000)",
    ),
    # 1. counts — hegel
    (
        r"\.test_cases\(\d[\d_]*\)",
        ".test_cases(40_000_000)",
    ),
    # 2. drop hegel seeds
    (
        r"\.seed\(Some\(0x[0-9A-Fa-f_]+\)\)",
        "",
    ),
    # 3. strip framework prefixes
    (
        r'"quickcheck counterexample: \(\{\}\)"',
        '"({})"',
    ),
    (
        r'"quickcheck failed with counterexample: \(\{\}\)"',
        '"({})"',
    ),
    (
        r'"crabcheck counterexample: \(\{\}\)"',
        '"({})"',
    ),
    (
        r'"crabcheck failed with counterexample: \(\{\}\)"',
        '"({})"',
    ),
    # 4. replace "hegel found counterexample: {msg}" with msg-with-prefix-stripped.
    # Keep the handler shape as-is; the surrounding block already owns `msg`.
    (
        r'Err\(format!\("hegel found counterexample: \{msg\}"\)\)',
        'Err(msg.strip_prefix("Property test failed: ").unwrap_or(&msg).to_string())',
    ),
    # 5. import TestError (add after TestCaseError if absent)
    (
        r"use proptest::test_runner::\{Config as ProptestConfig, TestCaseError, TestRunner\};",
        "use proptest::test_runner::{Config as ProptestConfig, TestCaseError, TestError, TestRunner};",
    ),
    # nom-rs has a variant without TestRunner in the use list.
    (
        r"use proptest::test_runner::\{Config as ProptestConfig, TestCaseError\};",
        "use proptest::test_runner::{Config as ProptestConfig, TestCaseError, TestError};",
    ),
    # 5. map_err(|e| e.to_string()) → pattern-match TestError::Fail
    (
        r"\.map_err\(\|e\| e\.to_string\(\)\)",
        ".map_err(|e| match e { TestError::Fail(reason, _) => reason.to_string(), other => other.to_string() })",
    ),
]


def retune(path: Path) -> list[str]:
    src = path.read_text()
    changed: list[str] = []
    for pat, repl in REPLACEMENTS:
        new, n = re.subn(pat, repl, src)
        if n:
            changed.append(f"  {pat!r}  x{n}")
            src = new
    path.write_text(src)
    return changed


def main() -> None:
    for wl in WORKLOADS:
        path = find_etna_rs(wl)
        edits = retune(path)
        print(f"{wl} ({path.name}):")
        if not edits:
            print("  no changes")
            continue
        for e in edits:
            print(e)


if __name__ == "__main__":
    main()
