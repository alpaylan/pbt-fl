#!/usr/bin/env python3
"""Validate a Haskell ETNA workload's manifest/source/patch consistency.

Mirrors what `scripts/check_python_workload.py` does for Python and what
`etna workload check` does for Rust. Used by the Haskell overnight
pipeline (etna-ify/prompts/run-haskell.md) and the Haskell pre-commit
hook (scripts/workload_precommit_haskell.sh).

Checks performed (all hard errors unless flagged --soft):
  1. etna.toml parses and declares language = "haskell".
  2. Every [[tasks]] group has [tasks.injection] with kind = "patch" and
     a patch file that exists on disk.
  3. Every patch applies cleanly in --check -R mode (i.e. base tree is
     the fixed state and reversing the patch produces the buggy state).
  4. Every PascalCase property name maps to a `property_<snake>` binding
     in etna/src/Etna/Properties.hs.
  5. Every PascalCase property name has a matching generator/series
     binding in each of:
       etna/src/Etna/Gens/QuickCheck.hs   (gen_<snake>)
       etna/src/Etna/Gens/Hedgehog.hs     (gen_<snake>)
       etna/src/Etna/Gens/Falsify.hs      (gen_<snake>)
       etna/src/Etna/Gens/SmallCheck.hs   (series_<snake>)
     unless the manifest annotates the variant with the corresponding
     `<backend>_dropped = true` flag (which excludes that backend from
     that variant only).
  6. Every [[tasks.tasks]].witnesses[].test_fn is a top-level binding
     in etna/src/Etna/Witnesses.hs of type PropertyResult.
  7. etna/app/Main.hs's `allProperties` list matches the manifest exactly.
  8. BUGS.md and TASKS.md exist (regen with `etna workload doc <dir>` if
     they're out of date — this script does NOT regen automatically;
     use --regen-docs to opt in).
  9. progress.jsonl, if present, parses as JSONL.

Usage:
    python scripts/check_haskell_workload.py <workload_dir>
    python scripts/check_haskell_workload.py <workload_dir> --regen-docs
    python scripts/check_haskell_workload.py <workload_dir> --soft

Exit codes:
    0  all checks passed
    1  one or more hard checks failed
    2  argv / I/O error
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

PASCAL_RE = re.compile(r"(?<!^)(?=[A-Z])")

# Match a top-level Haskell binding like:
#   property_foo_bar :: ...
#   property_foo_bar args = ...
# Names start a line (column 0); type signatures and equations both count
# as "defined". This is intentionally lenient — we only need to know that
# the name is bound at top level.
HS_BINDING_RE = re.compile(r"^([a-z][A-Za-z0-9_']*)\b", re.MULTILINE)

GEN_MODULES: list[tuple[str, str, str]] = [
    # (manifest-flag, module-relpath, prefix)
    ("quickcheck", "etna/src/Etna/Gens/QuickCheck.hs", "gen_"),
    ("hedgehog",   "etna/src/Etna/Gens/Hedgehog.hs",   "gen_"),
    ("falsify",    "etna/src/Etna/Gens/Falsify.hs",    "gen_"),
    ("smallcheck", "etna/src/Etna/Gens/SmallCheck.hs", "series_"),
]


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
        # property -> set of dropped backends (flag like "smallcheck_dropped = true")
        dropped_backends = self._collect_manifest_dropped_backends(manifest)

        self._check_patches(variants_in_manifest)
        self._check_properties_module(properties_in_manifest)
        self._check_generator_modules(properties_in_manifest, dropped_backends)
        self._check_witnesses_module(witnesses_in_manifest)
        self._check_main_module(properties_in_manifest)
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
        if lang != "haskell":
            self.fail(f'etna.toml: language must be "haskell", got {lang!r}')

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
                self.fail(
                    f"injection kind {kind!r}: only 'patch' supported for haskell"
                )
                continue
            if not patch:
                self.fail("injection has no patch field")
                continue
            for variant in group.get("mutations", []):
                out.append((variant, patch))
        return out

    def _collect_manifest_dropped_backends(self, manifest: dict) -> dict[str, set[str]]:
        """Return property -> set of backends excluded from this property.

        Two recognised forms:
          [[tasks.tasks]]
          property = "Foo"
          smallcheck_dropped = true

          [[dropped_for_backend]]
          property = "Foo"
          backend = "smallcheck"
        """
        dropped: dict[str, set[str]] = {}
        for group in manifest.get("tasks", []):
            for t in group.get("tasks", []):
                p = t.get("property")
                if not p:
                    continue
                for backend, _, _ in GEN_MODULES:
                    if t.get(f"{backend}_dropped") is True:
                        dropped.setdefault(p, set()).add(backend)
        for entry in manifest.get("dropped_for_backend", []):
            p = entry.get("property")
            b = entry.get("backend")
            if p and b:
                dropped.setdefault(p, set()).add(b)
        return dropped

    # ---- patch checks ----------------------------------------------------

    def _check_patches(self, variants: list[tuple[str, str]]) -> None:
        for variant, patch_rel in variants:
            patch_path = self.root / patch_rel
            if not patch_path.exists():
                self.fail(f"variant {variant}: patch file missing: {patch_rel}")
                continue
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

    # ---- haskell module introspection ------------------------------------

    def _module_bindings(self, rel_path: str) -> set[str] | None:
        path = self.root / rel_path
        if not path.exists():
            self.fail(f"missing module: {rel_path}")
            return None
        try:
            text = path.read_text()
        except OSError as e:
            self.fail(f"{rel_path}: read error: {e}")
            return None
        # Strip line comments to avoid matching `-- property_foo_bar` etc.
        cleaned_lines = []
        for line in text.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("--"):
                cleaned_lines.append("")
            else:
                cleaned_lines.append(line)
        cleaned = "\n".join(cleaned_lines)
        return set(HS_BINDING_RE.findall(cleaned))

    def _check_properties_module(self, props: set[str]) -> None:
        defs = self._module_bindings("etna/src/Etna/Properties.hs")
        if defs is None:
            return
        for prop in props:
            want = f"property_{pascal_to_snake(prop)}"
            if want not in defs:
                self.fail(
                    f"etna/src/Etna/Properties.hs: missing binding {want} "
                    f"(for manifest property {prop!r})"
                )

    def _check_generator_modules(
        self,
        props: set[str],
        dropped: dict[str, set[str]],
    ) -> None:
        for backend, rel_path, prefix in GEN_MODULES:
            defs = self._module_bindings(rel_path)
            if defs is None:
                continue
            for prop in props:
                if backend in dropped.get(prop, set()):
                    continue
                want = f"{prefix}{pascal_to_snake(prop)}"
                if want not in defs:
                    self.fail(
                        f"{rel_path}: missing binding {want} "
                        f"(for manifest property {prop!r}; mark "
                        f"`{backend}_dropped = true` to exclude this "
                        f"backend for this property)"
                    )

    def _check_witnesses_module(self, witnesses: set[str]) -> None:
        defs = self._module_bindings("etna/src/Etna/Witnesses.hs")
        if defs is None:
            return
        for w in witnesses:
            if w not in defs:
                self.fail(
                    f"etna/src/Etna/Witnesses.hs: missing binding {w}"
                )

    def _check_main_module(self, props: set[str]) -> None:
        path = self.root / "etna/app/Main.hs"
        if not path.exists():
            self.fail("missing module: etna/app/Main.hs")
            return
        try:
            text = path.read_text()
        except OSError as e:
            self.fail(f"etna/app/Main.hs: read error: {e}")
            return

        # Find `allProperties = [ "Foo", "Bar", ... ]` (single- or multi-line).
        # We accept any whitespace and trailing comments.
        m = re.search(
            r"allProperties\s*(?:::[^\n=]*)?=\s*\[(.*?)\]",
            text,
            re.DOTALL,
        )
        if not m:
            self.fail(
                "etna/app/Main.hs: `allProperties` not found "
                "(expected a top-level binding `allProperties = [\"...\", ...]`)"
            )
            return
        body = m.group(1)
        runner_props = set(re.findall(r'"([^"\\]*)"', body))

        if runner_props != props:
            extra = runner_props - props
            missing = props - runner_props
            if extra:
                self.fail(
                    f"etna/app/Main.hs: allProperties contains entries not "
                    f"in manifest: {sorted(extra)}"
                )
            if missing:
                self.fail(
                    f"etna/app/Main.hs: allProperties missing manifest "
                    f"entries: {sorted(missing)}"
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
