#!/usr/bin/env python3
"""Validate a Python ETNA workload's manifest/source/patch consistency.

Mirrors what `etna workload check` does for Rust workloads. Used by the
Python overnight pipeline (etna-ify/prompts/run-python.md) and the
Python pre-commit hook (scripts/workload_precommit_python.sh).

Checks performed (all hard errors unless flagged --soft):
  1. etna.toml parses and declares language = "python".
  2. Every [[tasks]] group has a [tasks.injection] with kind = "patch" and
     a patch file that exists on disk.
  3. Every patch applies cleanly in --check mode (forward) — i.e. base tree
     matches the patch's "from" side.
  4. Every PascalCase property name maps to a `def property_<snake>` in
     etna/properties.py, and a `def strategy_<snake>` in etna/strategies.py.
  5. Every [[tasks.tasks]].witnesses[].test_fn is a `def witness_*` in
     etna/witnesses.py with zero positional args.
  6. etna/runner.py's ALL_PROPERTIES list matches the manifest exactly.
  7. BUGS.md and TASKS.md exist (regen with `etna workload doc <dir>` if
     they're out of date — this script does NOT regen automatically; use
     --regen-docs to opt in).
  8. progress.jsonl, if present, parses as JSONL.

Usage:
    python scripts/check_python_workload.py <workload_dir>
    python scripts/check_python_workload.py <workload_dir> --regen-docs
    python scripts/check_python_workload.py <workload_dir> --soft  # warn only

Exit codes:
    0  all checks passed
    1  one or more hard checks failed
    2  argv / I/O error
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

PASCAL_RE = re.compile(r"(?<!^)(?=[A-Z])")


def pascal_to_snake(s: str) -> str:
    return PASCAL_RE.sub("_", s).lower()


class Checker:
    def __init__(self, root: Path, soft: bool = False) -> None:
        self.root = root
        self.soft = soft
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def fail(self, msg: str) -> None:
        target = self.warnings if self.soft else self.errors
        target.append(f"{self.root}: {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(f"{self.root}: {msg}")

    def run(self) -> int:
        manifest = self._load_manifest()
        if manifest is None:
            return self._report()

        self._check_language(manifest)
        properties_in_manifest = self._collect_manifest_properties(manifest)
        witnesses_in_manifest = self._collect_manifest_witnesses(manifest)
        variants_in_manifest = self._collect_manifest_variants(manifest)

        self._check_patches(variants_in_manifest)
        self._check_properties_module(properties_in_manifest)
        self._check_strategies_module(properties_in_manifest)
        self._check_witnesses_module(witnesses_in_manifest)
        self._check_runner_module(properties_in_manifest)
        self._check_docs()
        self._check_progress_jsonl()

        return self._report()

    # ---- loaders ---------------------------------------------------------

    def _load_manifest(self) -> dict | None:
        path = self.root / "etna.toml"
        if not path.exists():
            self.fail("etna.toml not found")
            return None
        try:
            with path.open("rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            self.fail(f"etna.toml: parse error: {e}")
            return None

    def _check_language(self, manifest: dict) -> None:
        lang = manifest.get("language")
        if lang != "python":
            self.fail(f'etna.toml: language must be "python", got {lang!r}')

    def _collect_manifest_properties(self, manifest: dict) -> set[str]:
        props: set[str] = set()
        for group in manifest.get("tasks", []):
            for t in group.get("tasks", []):
                p = t.get("property")
                if p:
                    props.add(p)
        return props

    def _collect_manifest_witnesses(self, manifest: dict) -> set[str]:
        ws: set[str] = set()
        for group in manifest.get("tasks", []):
            for t in group.get("tasks", []):
                for w in t.get("witnesses", []):
                    name = w.get("test_fn")
                    if name:
                        ws.add(name)
        return ws

    def _collect_manifest_variants(self, manifest: dict) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for group in manifest.get("tasks", []):
            inj = group.get("injection", {})
            kind = inj.get("kind")
            patch = inj.get("patch")
            if kind != "patch":
                self.fail(f"injection kind {kind!r}: only 'patch' supported for python")
                continue
            if not patch:
                self.fail("injection has no patch field")
                continue
            for variant in group.get("mutations", []):
                out.append((variant, patch))
        return out

    # ---- patch checks ----------------------------------------------------

    def _check_patches(self, variants: list[tuple[str, str]]) -> None:
        for variant, patch_rel in variants:
            patch_path = self.root / patch_rel
            if not patch_path.exists():
                self.fail(f"variant {variant}: patch file missing: {patch_rel}")
                continue
            # The patch records fix→buggy as a forward diff if generated
            # via `git format-patch -1 <fix-sha>`. We expect it to apply
            # in REVERSE against the (fixed) base tree.
            res = subprocess.run(
                ["git", "-C", str(self.root), "apply", "--check", "-R",
                 "--whitespace=nowarn", str(patch_path)],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                self.fail(
                    f"variant {variant}: patch does not apply in reverse "
                    f"against base — patch may need re-synthesis. stderr: "
                    f"{res.stderr.strip()[:300]}"
                )

    # ---- python module introspection -------------------------------------

    def _module_defs(self, rel_path: str) -> set[str] | None:
        path = self.root / rel_path
        if not path.exists():
            self.fail(f"missing module: {rel_path}")
            return None
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as e:
            self.fail(f"{rel_path}: syntax error: {e}")
            return None
        return {
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def _check_properties_module(self, props: set[str]) -> None:
        defs = self._module_defs("etna/etna_runner/properties.py")
        if defs is None:
            return
        for prop in props:
            want = f"property_{pascal_to_snake(prop)}"
            if want not in defs:
                self.fail(
                    f"etna/properties.py: missing function {want}() "
                    f"(for manifest property {prop!r})"
                )

    def _check_strategies_module(self, props: set[str]) -> None:
        defs = self._module_defs("etna/etna_runner/strategies.py")
        if defs is None:
            return
        for prop in props:
            want = f"strategy_{pascal_to_snake(prop)}"
            if want not in defs:
                self.fail(
                    f"etna/strategies.py: missing function {want}() "
                    f"(for manifest property {prop!r})"
                )

    def _check_witnesses_module(self, witnesses: set[str]) -> None:
        path = self.root / "etna/etna_runner/witnesses.py"
        if not path.exists():
            self.fail("missing module: etna/witnesses.py")
            return
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as e:
            self.fail(f"etna/witnesses.py: syntax error: {e}")
            return
        defs = {
            node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for w in witnesses:
            if w not in defs:
                self.fail(f"etna/witnesses.py: missing witness {w}()")
                continue
            fn = defs[w]
            if (fn.args.args or fn.args.vararg or fn.args.kwarg
                    or fn.args.kwonlyargs or fn.args.posonlyargs):
                self.fail(
                    f"etna/witnesses.py: witness {w}() must take no "
                    f"arguments (got {len(fn.args.args)})"
                )

    def _check_runner_module(self, props: set[str]) -> None:
        path = self.root / "etna/etna_runner/runner.py"
        if not path.exists():
            self.fail("missing module: etna/runner.py")
            return
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as e:
            self.fail(f"etna/runner.py: syntax error: {e}")
            return
        # Find ALL_PROPERTIES = [...]
        runner_props: set[str] | None = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id == "ALL_PROPERTIES"
                    and isinstance(node.value, ast.List)):
                items = []
                ok = True
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        items.append(elt.value)
                    else:
                        ok = False
                        break
                if ok:
                    runner_props = set(items)
                    break
        if runner_props is None:
            self.fail(
                "etna/runner.py: ALL_PROPERTIES not a top-level "
                "assignment to a list of string literals"
            )
            return
        if runner_props != props:
            extra_in_runner = runner_props - props
            missing_in_runner = props - runner_props
            if extra_in_runner:
                self.fail(
                    f"etna/runner.py: ALL_PROPERTIES contains entries not "
                    f"in manifest: {sorted(extra_in_runner)}"
                )
            if missing_in_runner:
                self.fail(
                    f"etna/runner.py: ALL_PROPERTIES missing manifest "
                    f"entries: {sorted(missing_in_runner)}"
                )

    # ---- docs / progress -------------------------------------------------

    def _check_docs(self) -> None:
        for name in ("BUGS.md", "TASKS.md"):
            if not (self.root / name).exists():
                self.fail(f"{name} not found (regen with `etna workload doc .`)")

    def _check_progress_jsonl(self) -> None:
        path = self.root / "progress.jsonl"
        if not path.exists():
            return
        try:
            with path.open() as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as e:
                        self.warn(f"progress.jsonl:{i}: invalid JSON: {e}")
                        return
        except OSError as e:
            self.warn(f"progress.jsonl: read error: {e}")

    # ---- output ----------------------------------------------------------

    def _report(self) -> int:
        for w in self.warnings:
            print(f"warning: {w}", file=sys.stderr)
        for e in self.errors:
            print(f"error: {e}", file=sys.stderr)
        if self.errors:
            return 1
        print(f"{self.root}: ok ({len(self.warnings)} warnings)")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("dir", help="Workload directory containing etna.toml")
    p.add_argument("--soft", action="store_true",
                   help="Convert errors to warnings (exit 0 even on findings)")
    p.add_argument("--regen-docs", action="store_true",
                   help="Run `etna workload doc <dir>` before checking")
    args = p.parse_args()

    root = Path(args.dir).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    if args.regen_docs:
        res = subprocess.run(["etna", "workload", "doc", str(root)],
                             capture_output=True, text=True)
        if res.returncode != 0:
            print(f"warning: etna workload doc failed: {res.stderr.strip()}",
                  file=sys.stderr)
        else:
            print(res.stdout.strip())

    return Checker(root, soft=args.soft).run()


if __name__ == "__main__":
    sys.exit(main())
