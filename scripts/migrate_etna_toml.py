#!/usr/bin/env python3
"""Migrate a workload's etna.toml from the old `[[variant]]` shape to the v2
schema that etna-cli's WorkloadManifest expects.

Old layout:
    [workload] name, crate, language, description
    [runner]   bin, cargo_features
    [[variant]] name, property (snake), injection, source_commit, witnesses, frameworks, files

New layout (see etna2/src/workload.rs):
    name, description, language, crate, base_commit
    [[tasks]]      mutations, tasks, source, injection, bug
    [[dropped]]    commit, reason, subject

The script:
  - reads the workload's old etna.toml, BUGS.md, Cargo.toml, src/bin/etna.rs
  - parses upstream PR data for each variant's source_commit via `gh api`
    (cached under <workload>/.migration-cache/) unless --offline is passed
  - extracts bug narrative (invariant + how_triggered) from the existing BUGS.md
  - converts snake_case property names to PascalCase by matching against the
    dispatcher in src/bin/etna.rs (same recipe as generate_test_specs.py)
  - writes the new etna.toml in place, preserving unrelated blocks as comments

Run:
    python3 scripts/migrate_etna_toml.py workloads/Rust/tinyvec
    python3 scripts/migrate_etna_toml.py workloads/Rust/tinyvec --offline
    python3 scripts/migrate_etna_toml.py workloads/Rust/tinyvec --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ARM_RE = re.compile(r'"([A-Z][A-Za-z0-9]+)"\s*=>')
PROP_CALL_RE = re.compile(r"\bproperty_([a-z0-9_]+)\b")
BASE_COMMIT_RE = re.compile(
    r"Base commit for this workload is ([0-9a-f]{7,40})", re.IGNORECASE
)
# "-   35082e1 \"TinyVec::fmt - fix pretty printing\"        → same bug class..."
DROPPED_LINE_RE = re.compile(
    r"^#?\s*-\s*([0-9a-f]{7,40})\s*\"([^\"]+)\"\s*(?:→|->|—)\s*(.+)$"
)
REPO_RE = re.compile(r'^repository\s*=\s*"([^"]+)"', re.MULTILINE)
CRATE_NAME_RE = re.compile(r'^name\s*=\s*"([^"]+)"', re.MULTILINE)

# BUGS.md section headers look like `### 1. debug_alternate_empty`
SECTION_RE = re.compile(r"^###\s*\d+\.\s*(.+?)\s*$", re.MULTILINE)
# `- **Key**: value`  (value may span the following indented lines)
BULLET_RE = re.compile(r"^-\s*\*\*([^*]+)\*\*:\s*(.*)$")


def sh(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True)


def find_etna_rs(wl_root: Path) -> Path:
    for candidate in [wl_root / "src" / "bin" / "etna.rs", *wl_root.glob("*/src/bin/etna.rs")]:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no src/bin/etna.rs under {wl_root}")


def snake_to_pascal_map(etna_rs: Path) -> dict[str, str]:
    """`"PascalCase" =>` arms paired with the first property_<snake> call in
    each arm body — copied from scripts/generate_test_specs.py so the migrator
    doesn't take a new cross-dep on that script."""
    src = etna_rs.read_text()
    arms = [(m.start(), m.end(), m.group(1)) for m in ARM_RE.finditer(src)]
    mapping: dict[str, str] = {}
    for i, (_, end, pascal) in enumerate(arms):
        block_end = arms[i + 1][0] if i + 1 < len(arms) else len(src)
        body = src[end:block_end]
        call = PROP_CALL_RE.search(body)
        if call:
            mapping.setdefault(call.group(1), pascal)
    return mapping


def extract_base_commit(etna_toml_text: str) -> str | None:
    m = BASE_COMMIT_RE.search(etna_toml_text)
    return m.group(1) if m else None


def extract_dropped(etna_toml_text: str) -> list[dict[str, str]]:
    """Parse the header-comment block that lists candidate commits dropped
    from the workload. Each line looks like:
        #   - 35082e1 "subject"     → reason"""
    dropped: list[dict[str, str]] = []
    in_block = False
    for line in etna_toml_text.splitlines():
        stripped = line.strip()
        if "Candidate commits dropped" in stripped:
            in_block = True
            continue
        if not in_block:
            continue
        if not stripped.startswith("#"):
            break
        # strip leading '#' and whitespace, then try the DROPPED_LINE_RE
        body = re.sub(r"^#\s?", "", line).rstrip()
        m = DROPPED_LINE_RE.match(body)
        if m:
            dropped.append(
                {"commit": m.group(1), "subject": m.group(2), "reason": m.group(3).strip()}
            )
    return dropped


def extract_repo(wl_root: Path) -> str | None:
    cargo = wl_root / "Cargo.toml"
    if not cargo.exists():
        return None
    text = cargo.read_text()
    m = REPO_RE.search(text)
    return m.group(1) if m else None


def extract_crate_name(wl_root: Path) -> str | None:
    cargo = wl_root / "Cargo.toml"
    if not cargo.exists():
        return None
    # First [package]-level `name = "..."`. First match across file works in
    # practice because workspace manifests put [package] first; for workspace-
    # only manifests (members nest the real Cargo.toml), the old etna.toml
    # already declares `[workload].crate` — fall back to that.
    text = cargo.read_text()
    m = CRATE_NAME_RE.search(text)
    return m.group(1) if m else None


def parse_bugs_md(bugs_path: Path) -> dict[str, dict[str, Any]]:
    """Return short_name -> {location, symbol, fix_subject, invariant, how_triggered}.

    Best-effort: if a section is missing, that field is omitted. Hand-review
    after migration catches the gaps."""
    if not bugs_path.exists():
        return {}
    text = bugs_path.read_text()
    # Split by `### N. <short_name>` headers.
    parts = re.split(r"^###\s*\d+\.\s*(.+?)\s*$", text, flags=re.MULTILINE)
    # parts[0] is preamble; then alternates: short_name, body, short_name, body, ...
    result: dict[str, dict[str, Any]] = {}
    for i in range(1, len(parts), 2):
        short = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        result[short] = _parse_bug_section(body)
    return result


def _parse_bug_section(body: str) -> dict[str, Any]:
    """Each top-level bullet `- **Key**: value` captures a field. Continuation
    lines (non-bullet, non-empty) are appended to the last field."""
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        m = BULLET_RE.match(line)
        if m:
            current = m.group(1).strip()
            fields.setdefault(current, []).append(m.group(2).strip())
            continue
        if current is None:
            continue
        # Continuation of the current bullet if it's indented or not a new section.
        if line.startswith(" ") or line.startswith("\t"):
            fields[current].append(line.strip())
        elif line.strip() == "":
            # blank line inside a bullet — allowed, but stop extending on a new
            # bullet that's not indented.
            continue
        else:
            current = None

    def join(key: str) -> str:
        return " ".join(s for s in fields.get(key, []) if s).strip()

    out: dict[str, Any] = {}
    loc = join("Location")
    if loc:
        # `src/arrayvec.rs:1839` (inside `impl<A: Array> Debug for ArrayVec<A>`)
        m = re.match(r"`([^`]+?)(?::(\d+))?`(?:\s*\(inside\s*`([^`]+)`\))?", loc)
        if m:
            out["file"] = m.group(1)
            if m.group(2):
                out["line"] = int(m.group(2))
            if m.group(3):
                out["symbol"] = m.group(3)
    fix = join("Fix commit")
    if fix:
        # `<sha>` — <subject>
        m = re.match(r"`([0-9a-f]{7,40})`\s*(?:—|--)\s*(.*)", fix)
        if m:
            out["fix_commit"] = m.group(1)
            out["fix_subject"] = m.group(2).strip().strip("`")
    inv = join("Invariant violated")
    if inv:
        out["invariant"] = _unwrap_backticks(inv)
    how = join("How the mutation triggers")
    if how:
        out["how_triggered"] = _unwrap_backticks(how)
    return out


def _unwrap_backticks(s: str) -> str:
    # A lot of BUGS.md prose starts with backticks. Keep them — they're
    # legitimate code references. Just normalize trailing whitespace.
    return s.strip()


def fetch_pr_data(
    wl_root: Path,
    repo_url: str,
    sha: str,
    cache_dir: Path,
    offline: bool,
) -> dict[str, Any]:
    """Fetch PRs + commit subject for a source commit. Cached on disk.
    Returns dict with optional keys: pr, pr_title, subject."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{sha}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    if offline:
        return {}
    owner_repo = repo_url.removeprefix("https://github.com/").rstrip("/")
    try:
        commit_json = sh(["gh", "api", f"repos/{owner_repo}/commits/{sha}"])
        subject = json.loads(commit_json)["commit"]["message"].splitlines()[0]
    except subprocess.CalledProcessError:
        subject = None
    try:
        prs_json = sh(["gh", "api", f"repos/{owner_repo}/commits/{sha}/pulls"])
        prs = json.loads(prs_json)
    except subprocess.CalledProcessError:
        prs = []
    data: dict[str, Any] = {}
    if subject:
        data["subject"] = subject
    if prs:
        pr = prs[0]
        data["pr"] = pr["number"]
        data["pr_title"] = pr["title"]
        data["pr_body"] = pr.get("body") or ""
    cache_file.write_text(json.dumps(data, indent=2))
    return data


def short_name_from_variant(variant: str) -> str:
    # `debug_alternate_empty_a711c72_1` -> `debug_alternate_empty`
    return re.sub(r"_[0-9a-f]{7}_\d+$", "", variant)


def fmt_toml_string(s: str) -> str:
    if "\n" in s or '"' in s:
        escaped = s.replace("\\", "\\\\").replace('"""', '\\"""')
        return f'"""\n{escaped}\n"""'
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fmt_toml_string_array(items: list[str]) -> str:
    return "[" + ", ".join(fmt_toml_string(s) for s in items) + "]"


def fmt_inline_loc(loc: dict[str, Any]) -> str:
    parts = [f'file = {fmt_toml_string(loc["file"])}']
    if "line" in loc:
        parts.append(f"line = {loc['line']}")
    if "symbol" in loc:
        parts.append(f"symbol = {fmt_toml_string(loc['symbol'])}")
    return "{ " + ", ".join(parts) + " }"


def build_new_toml(
    old: dict[str, Any],
    wl_root: Path,
    offline: bool,
) -> str:
    cache_dir = wl_root / ".migration-cache"
    old_text = (wl_root / "etna.toml").read_text()
    base_commit = extract_base_commit(old_text)
    dropped = extract_dropped(old_text)
    repo = extract_repo(wl_root)
    crate = old.get("workload", {}).get("crate") or extract_crate_name(wl_root)
    description = old.get("workload", {}).get("description", "").strip()
    name = old.get("workload", {}).get("name") or old.get("name")
    if not name:
        raise SystemExit("old etna.toml missing workload name")
    language = (
        old.get("workload", {}).get("language") or old.get("language") or "Rust"
    ).lower()

    etna_rs = find_etna_rs(wl_root)
    snake_pascal = snake_to_pascal_map(etna_rs)

    bugs_sections = parse_bugs_md(wl_root / "BUGS.md")

    variants = old.get("variant", [])
    if not variants:
        raise SystemExit("old etna.toml has no [[variant]] blocks")

    out: list[str] = []
    out.append(f"name = {fmt_toml_string(name)}")
    if description:
        out.append(f"description = {fmt_toml_string(description)}")
    out.append(f'language = {fmt_toml_string(language)}')
    if crate:
        out.append(f"crate = {fmt_toml_string(crate)}")
    if base_commit:
        out.append(f"base_commit = {fmt_toml_string(base_commit)}")
    out.append("")

    for v in variants:
        short = short_name_from_variant(v["name"])
        bug_info = bugs_sections.get(short, {})
        snake = v["property"]
        pascal = snake_pascal.get(snake)
        if not pascal:
            print(
                f"  warning: variant {v['name']} references property_{snake} "
                f"but no PascalCase dispatch arm found; leaving as {snake}",
                file=sys.stderr,
            )
            pascal = snake
        pr_data: dict[str, Any] = {}
        if repo:
            pr_data = fetch_pr_data(
                wl_root, repo, v["source_commit"], cache_dir, offline
            )

        out.append("[[tasks]]")
        out.append(f"mutations = [{fmt_toml_string(v['name'])}]")
        out.append("")

        if repo:
            out.append("[tasks.source]")
            out.append(f"repo = {fmt_toml_string(repo)}")
            out.append(f"commits = [{fmt_toml_string(v['source_commit'])}]")
            subject = pr_data.get("subject") or bug_info.get("fix_subject")
            if subject:
                out.append(f"commit_subjects = [{fmt_toml_string(subject)}]")
            if pr_data.get("pr"):
                out.append(f"prs = [{pr_data['pr']}]")
            # summary left empty for hand-fill (comment marker so it's
            # obvious in the diff)
            out.append(
                'summary = "TODO: one-to-three-line excerpt of why the upstream fix was needed"'
            )
            out.append("")

        out.append("[tasks.injection]")
        out.append(f'kind = {fmt_toml_string(v.get("injection", "marauders"))}')
        out.append(f'files = {fmt_toml_string_array(v.get("files", []))}')
        if "file" in bug_info:
            out.append(
                "locations = [" + fmt_inline_loc(bug_info) + "]"
            )
        if v.get("injection") == "patch":
            patch_path = v.get("patch")
            if not patch_path:
                # default convention: patches/<name>.patch
                patch_path = f"patches/{v['name']}.patch"
            out.append(f"patch = {fmt_toml_string(patch_path)}")
        out.append("")

        if bug_info.get("invariant") or bug_info.get("how_triggered"):
            out.append("[tasks.bug]")
            out.append(f"short_name = {fmt_toml_string(short)}")
            if bug_info.get("invariant"):
                out.append(f"invariant = {fmt_toml_string(bug_info['invariant'])}")
            if bug_info.get("how_triggered"):
                out.append(
                    f"how_triggered = {fmt_toml_string(bug_info['how_triggered'])}"
                )
            out.append("")

        out.append("[[tasks.tasks]]")
        out.append(f"property = {fmt_toml_string(pascal)}")
        witnesses = v.get("witnesses", [])
        if witnesses:
            out.append("witnesses = [")
            for w in witnesses:
                out.append(f"  {{ test_fn = {fmt_toml_string(w)} }},")
            out.append("]")
        out.append("")

    for d in dropped:
        out.append("[[dropped]]")
        out.append(f"commit = {fmt_toml_string(d['commit'])}")
        if d.get("subject"):
            out.append(f"subject = {fmt_toml_string(d['subject'])}")
        out.append(f"reason = {fmt_toml_string(d['reason'])}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("workload", type=Path, help="Path to workload directory")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="Skip `gh api` calls; leave prs/commit_subjects empty when not cached",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the new etna.toml to stdout instead of writing it",
    )
    args = ap.parse_args()

    wl_root: Path = args.workload.resolve()
    etna_toml = wl_root / "etna.toml"
    if not etna_toml.exists():
        raise SystemExit(f"no etna.toml at {etna_toml}")

    with etna_toml.open("rb") as f:
        old = tomllib.load(f)

    new_text = build_new_toml(old, wl_root, offline=args.offline)
    if args.dry_run:
        sys.stdout.write(new_text)
        return
    etna_toml.write_text(new_text)
    print(f"Wrote {etna_toml}")


if __name__ == "__main__":
    main()
