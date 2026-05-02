#!/usr/bin/env python3
"""Scaffold the etna/ skeleton for a new Python workload.

Idempotent. Creates etna/{__init__.py,_result.py,properties.py,
strategies.py,witnesses.py,runner.py,pyproject.toml,tests/} plus a
.gitignore entry for progress.jsonl. Does NOT mutate upstream files.

Used by the overnight pipeline (run-python.md) on a fresh clone, and by
hand when bootstrapping a new candidate.

Usage:
    python scripts/scaffold_python_workload.py <workload_dir> --libname <import_name>

Example:
    python scripts/scaffold_python_workload.py workloads/Python/sortedcontainers \\
           --libname sortedcontainers
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PKG_INIT = '''"""ETNA runner package — generated. Edit properties.py / strategies.py / witnesses.py."""
'''

RESULT_PY = '''"""Framework-neutral PropertyResult, mirroring the Rust pipeline.

Pure data; no behavior. Property functions return one of PASS / DISCARD /
fail("reason"). The runner translates these into the JSON-on-stdout
contract described in etna-ify/prompts/run-python.md.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PropertyResult:
    kind: str           # "pass" | "fail" | "discard"
    message: str = ""

    @property
    def is_pass(self) -> bool: return self.kind == "pass"

    @property
    def is_fail(self) -> bool: return self.kind == "fail"


PASS = PropertyResult("pass")
DISCARD = PropertyResult("discard")


def fail(msg: str) -> PropertyResult:
    return PropertyResult("fail", msg)
'''

PROPERTIES_PY = '''"""Property functions — one `def property_<snake>(args) -> PropertyResult` per
manifest entry. Pure, total, deterministic. No I/O, no clock, no random.

Add new properties below as the atomize stage progresses. The PascalCase
manifest name maps to `property_<snake>` here via the standard mapping
(see scripts/check_python_workload.py:pascal_to_snake).
"""
from __future__ import annotations

from ._result import PropertyResult, PASS, DISCARD, fail

# Example skeleton — delete once real properties land:
# def property_example(args) -> PropertyResult:
#     a, b = args
#     if a + b == b + a:
#         return PASS
#     return fail(f"({a!r}, {b!r}): commutativity broken")
'''

STRATEGIES_PY = '''"""Hypothesis SearchStrategy builders — one `def strategy_<snake>()` per property.

CrossHair-compatible strategies only: stick to st.integers, st.text, st.lists,
st.tuples, st.booleans, st.from_type, st.builds, st.one_of. Avoid st.data,
st.randoms, and custom @composite that branches on intermediate state.

See etna-ify/prompts/run-python.md for the full compatibility guidance.
"""
from __future__ import annotations

from hypothesis import strategies as st

# Example skeleton:
# def strategy_example():
#     return st.tuples(st.integers(), st.integers())
'''

WITNESSES_PY = '''"""Witness functions — one `def witness_<snake>_case_<tag>() -> PropertyResult`
per witness in the manifest. Plain function, zero arguments, no decorators,
no randomness. Calls a property with frozen inputs.

Each witness must:
  * Pass on the base tree (PropertyResult.is_pass).
  * Fail when the corresponding patch is reverse-applied
    (PropertyResult.is_fail).

Validate both directions before declaring a variant done — see
"Property fidelity check" in etna-ify/prompts/run-python.md.
"""
from __future__ import annotations

from .properties import *  # noqa: F401,F403  -- re-export for runner introspection
from ._result import PropertyResult

# Example skeleton:
# def witness_example_case_zero() -> PropertyResult:
#     return property_example((0, 0))
'''

RUNNER_PY = '''"""ETNA runner for Python workloads.

Dispatches `<tool> <property>` programmatically. Emits a single JSON line
on stdout per invocation; always exits 0 except on argv-parse errors.

Tools:
  * etna       — replays every witness for the property.
  * hypothesis — Hypothesis default backend (random + shrinking).
  * crosshair  — Hypothesis with backend="crosshair" (symbolic).
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from hypothesis import HealthCheck, given, settings
from hypothesis.errors import HypothesisException

from . import properties, strategies, witnesses

# Keep ALL_PROPERTIES in sync with [[tasks.tasks]].property entries in
# etna.toml. scripts/check_python_workload.py asserts this equality.
ALL_PROPERTIES: list[str] = []


def _pascal_to_snake(s: str) -> str:
    out = []
    for i, c in enumerate(s):
        if c.isupper() and i and not s[i - 1].isupper():
            out.append("_")
        out.append(c.lower())
    return "".join(out)


def _emit(tool: str, prop: str, status: str, tests: int, time_us: int,
          counterexample: str | None = None, error: str | None = None) -> None:
    sys.stdout.write(json.dumps({
        "status": status, "tests": tests, "discards": 0,
        "time": f"{time_us}us",
        "counterexample": counterexample, "error": error,
        "tool": tool, "property": prop,
    }) + "\\n")
    sys.stdout.flush()


def _run_witness(prop: str) -> tuple[str, int, str | None]:
    snake = _pascal_to_snake(prop)
    fns = [getattr(witnesses, n) for n in dir(witnesses)
           if n.startswith(f"witness_{snake}_case_") and callable(getattr(witnesses, n))]
    if not fns:
        return ("aborted", 0, f"no witnesses for {prop}")
    for fn in fns:
        r = fn()
        if r.is_fail:
            return ("failed", 1, r.message)
    return ("passed", len(fns), None)


def _run_hypothesis(prop: str, backend: str, max_examples: int) -> tuple[str, int, str | None, str | None]:
    snake = _pascal_to_snake(prop)
    strat_fn = getattr(strategies, f"strategy_{snake}", None)
    prop_fn = getattr(properties, f"property_{snake}", None)
    if strat_fn is None or prop_fn is None:
        return ("aborted", 0, None, f"missing strategy or property for {prop}")
    counter = {"n": 0}
    counterexample: list[str | None] = [None]

    def _wrapped(args):
        counter["n"] += 1
        r = prop_fn(args)
        if r.is_fail:
            counterexample[0] = repr(args)
            assert False, r.message
        # Pass / Discard: return None.

    test = given(strat_fn())(_wrapped)
    test = settings(
        backend=backend,
        max_examples=max_examples,
        deadline=None,
        derandomize=False,
        suppress_health_check=list(HealthCheck),
        database=None,
    )(test)

    try:
        test()
        return ("passed", counter["n"], None, None)
    except AssertionError:
        return ("failed", counter["n"], counterexample[0] or "<unknown>", None)
    except HypothesisException as e:
        return ("failed", counter["n"], counterexample[0] or "<unknown>", str(e))
    except Exception as e:
        return ("failed", counter["n"], counterexample[0] or "<unknown>",
                f"{type(e).__name__}: {e}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("tool", choices=["etna", "hypothesis", "crosshair"])
    p.add_argument("property")
    p.add_argument("--max-examples", type=int, default=200)
    args = p.parse_args(argv)

    targets = ALL_PROPERTIES if args.property == "All" else [args.property]
    t0 = time.perf_counter()

    for prop in targets:
        if prop not in ALL_PROPERTIES:
            _emit(args.tool, prop, "aborted", 0, 0, None, f"unknown property: {prop}")
            continue
        if args.tool == "etna":
            status, tests, err = _run_witness(prop)
            cex = err if status == "failed" else None
            _emit(args.tool, prop, status, tests,
                  int((time.perf_counter() - t0) * 1e6), cex, None)
        else:
            backend = "crosshair" if args.tool == "crosshair" else "hypothesis"
            status, tests, cex, err = _run_hypothesis(prop, backend, args.max_examples)
            _emit(args.tool, prop, status, tests,
                  int((time.perf_counter() - t0) * 1e6), cex, err)

    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

PYPROJECT_TOML_TPL = '''[project]
name = "etna-runner-{libname}"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
  "hypothesis>=6.115",
  "hypothesis-crosshair>=0.0.20",
  "crosshair-tool>=0.0.79",
  "pytest>=8",
]

[project.scripts]
etna-runner = "etna_runner.runner:main"

[tool.uv.sources]
{libname} = {{ path = "..", editable = true }}

[tool.hatch.build.targets.wheel]
packages = ["etna_runner"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
'''

TESTS_INIT = ""

TESTS_WITNESSES = '''"""Pytest collection for witnesses. Lets `pytest` exercise every witness as
a base-tree sanity check (every witness must return PropertyResult.is_pass on
HEAD). The runner uses the witnesses module directly via tool=etna.
"""
from __future__ import annotations

import pytest

from etna_runner import witnesses


def _all_witnesses():
    return [
        (name, getattr(witnesses, name))
        for name in dir(witnesses)
        if name.startswith("witness_") and callable(getattr(witnesses, name))
    ]


@pytest.mark.parametrize("name,fn", _all_witnesses())
def test_witness_passes_on_base(name, fn):
    r = fn()
    assert r.is_pass, f"{name}: {r.message}"
'''

GITIGNORE_LINES = [
    "progress.jsonl",
    ".hegel/",
    ".pytest_cache/",
    ".ruff_cache/",
    "etna/__pycache__/",
    "etna/.venv/",
    # NOTE: etna/uv.lock is intentionally NOT ignored — pin hypothesis-crosshair
    # versions for reproducibility. The fork-push script enforces this.
    "etna/dist/",
    "etna/*.egg-info/",
]


def write_if_absent(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True


def append_gitignore(root: Path, lines: list[str]) -> int:
    gi = root / ".gitignore"
    existing = gi.read_text().splitlines() if gi.exists() else []
    have = set(l.strip() for l in existing)
    added = [l for l in lines if l not in have]
    if not added:
        return 0
    with gi.open("a") as f:
        if existing and not existing[-1].endswith(""):
            f.write("\n")
        f.write("\n# etna-ify additions\n")
        for l in added:
            f.write(l + "\n")
    return len(added)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("dir", help="Workload directory (e.g. workloads/Python/sortedcontainers)")
    p.add_argument("--libname", required=True,
                   help="Importable name of the upstream library (e.g. 'sortedcontainers')")
    args = p.parse_args()

    root = Path(args.dir).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    etna = root / "etna"
    pkg = etna / "etna_runner"
    pyproject = PYPROJECT_TOML_TPL.format(libname=args.libname)

    created = 0
    # Layout (see etna-ify/prompts/run-python.md):
    #   etna/pyproject.toml                       — uv project root
    #   etna/etna_runner/                         — installed package
    #   etna/tests/                               — pytest collection (separate)
    if write_if_absent(etna / "pyproject.toml", pyproject): created += 1
    if write_if_absent(pkg / "__init__.py", PKG_INIT): created += 1
    if write_if_absent(pkg / "_result.py", RESULT_PY): created += 1
    if write_if_absent(pkg / "properties.py", PROPERTIES_PY): created += 1
    if write_if_absent(pkg / "strategies.py", STRATEGIES_PY): created += 1
    if write_if_absent(pkg / "witnesses.py", WITNESSES_PY): created += 1
    if write_if_absent(pkg / "runner.py", RUNNER_PY): created += 1
    if write_if_absent(etna / "tests" / "__init__.py", TESTS_INIT): created += 1
    if write_if_absent(etna / "tests" / "test_witnesses.py", TESTS_WITNESSES): created += 1
    if write_if_absent(root / "patches" / ".gitkeep", ""): created += 1

    added = append_gitignore(root, GITIGNORE_LINES)

    print(f"{root}: scaffolded {created} new file(s), added {added} gitignore line(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
