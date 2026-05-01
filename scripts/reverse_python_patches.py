#!/usr/bin/env python3
"""Convert Python workload patches from "buggy→fixed" to "fixed→buggy" so that
forward-applying them (the way marauders activates a variant) injects the bug.

The overnight agents generated patches via `git format-patch -1 <FIX_SHA>`,
which encodes "buggy→fixed" — applying it forward against HEAD (which is the
post-fix base state) is a no-op or fails, because the fix is already there.
Marauders' patch-kind injector calls `git apply` forward without `-R`, so the
patches must be in the opposite orientation: forward-apply = inject bug.

For each patch:
  1. Reverse-apply against the (fixed) HEAD: working tree becomes buggy.
  2. `git diff -- <patch's files>` captures the fixed→buggy diff in the
     correct orientation.
  3. Forward-apply the original patch to restore (buggy→fixed).
  4. Overwrite the patch file with the captured diff.

Usage:
    python scripts/reverse_python_patches.py <workload_dir> [<workload_dir>...]
    python scripts/reverse_python_patches.py --all
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

FAULTLOC = Path(__file__).resolve().parent.parent


def patch_files(workload_dir: Path, patch_path: Path) -> list[str]:
    """Return the list of files affected by `patch_path` (per `git apply --numstat`)."""
    res = subprocess.run(
        ["git", "-C", str(workload_dir), "apply", "--numstat", str(patch_path)],
        capture_output=True, text=True, check=True,
    )
    files = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            files.append(parts[2])
    return files


def working_tree_clean_for(workload_dir: Path, files: list[str]) -> bool:
    """True iff the given files have no working-tree changes vs HEAD."""
    res = subprocess.run(
        ["git", "-C", str(workload_dir), "status", "--porcelain", "--"] + files,
        capture_output=True, text=True, check=True,
    )
    return res.stdout.strip() == ""


def reverse_one(workload_dir: Path, patch_path: Path, dry_run: bool = False) -> bool:
    """Returns True on success, False on skip (e.g. already in correct orientation)."""
    name = patch_path.name
    # Sanity check: forward-applying must currently fail and reverse-applying
    # must succeed. Otherwise the patch is already in the right shape, or
    # fundamentally broken.
    fwd_ok = subprocess.run(
        ["git", "-C", str(workload_dir), "apply", "--check",
         "--whitespace=nowarn", str(patch_path)],
        capture_output=True,
    ).returncode == 0
    rev_ok = subprocess.run(
        ["git", "-C", str(workload_dir), "apply", "--check", "-R",
         "--whitespace=nowarn", str(patch_path)],
        capture_output=True,
    ).returncode == 0

    if fwd_ok and not rev_ok:
        print(f"  {name}: already in correct orientation (forward applies, reverse doesn't); skipping")
        return False
    if not rev_ok:
        print(f"  {name}: reverse-apply fails — patch is broken, manual repair needed", file=sys.stderr)
        return False
    # rev_ok=True, fwd_ok=False — needs reversal.

    files = patch_files(workload_dir, patch_path)
    if not files:
        print(f"  {name}: no files extracted, skipping", file=sys.stderr)
        return False

    if not working_tree_clean_for(workload_dir, files):
        print(f"  {name}: working tree dirty for {files}, refusing to clobber", file=sys.stderr)
        return False

    if dry_run:
        print(f"  {name}: would reverse (touches {files})")
        return True

    # 1. Reverse-apply: HEAD (fixed) → working tree (buggy)
    subprocess.run(
        ["git", "-C", str(workload_dir), "apply", "-R", "--whitespace=nowarn", str(patch_path)],
        check=True,
    )
    try:
        # 2. Capture diff scoped to the affected files. This is the
        #    fixed→buggy direction = inject-bug direction.
        diff = subprocess.run(
            ["git", "-C", str(workload_dir), "diff", "--"] + files,
            capture_output=True, text=True, check=True,
        ).stdout
        if not diff.strip():
            print(f"  {name}: empty diff after reverse — patch was a no-op?", file=sys.stderr)
            return False
        # Use a tmp file so we don't half-overwrite on failure.
        tmp = patch_path.with_suffix(patch_path.suffix + ".tmp")
        tmp.write_text(diff)
    finally:
        # 3. Restore by forward-applying the (still original) patch:
        #    working (buggy) + buggy→fixed = fixed.
        subprocess.run(
            ["git", "-C", str(workload_dir), "apply", "--whitespace=nowarn", str(patch_path)],
            check=True,
        )

    # 4. Atomically replace.
    tmp.replace(patch_path)
    print(f"  {name}: reversed ({len(diff.splitlines())} lines)")

    # Sanity check: forward-apply should now succeed against HEAD.
    final_fwd_ok = subprocess.run(
        ["git", "-C", str(workload_dir), "apply", "--check",
         "--whitespace=nowarn", str(patch_path)],
        capture_output=True,
    ).returncode == 0
    if not final_fwd_ok:
        print(f"  {name}: WARNING — reversed patch still fails forward-apply", file=sys.stderr)
        return False
    return True


def reverse_workload(workload_dir: Path, dry_run: bool = False) -> tuple[int, int]:
    print(f"=== {workload_dir.name} ===")
    patches = sorted((workload_dir / "patches").glob("*.patch"))
    if not patches:
        print("  no patches")
        return (0, 0)
    ok = 0
    skipped = 0
    for p in patches:
        if reverse_one(workload_dir, p, dry_run=dry_run):
            ok += 1
        else:
            skipped += 1
    return (ok, skipped)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("workloads", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--dry-run", action="store_true",
                   help="Inspect patches but don't modify files")
    args = p.parse_args()
    if args.all:
        roots = sorted(
            d for d in (FAULTLOC / "workloads" / "Python").iterdir()
            if d.is_dir() and (d / "etna.toml").exists()
        )
    else:
        roots = [Path(w).resolve() for w in args.workloads]
    if not roots:
        p.error("no workloads given (pass paths or --all)")
    total_ok = 0
    total_skip = 0
    for w in roots:
        ok, skip = reverse_workload(w, dry_run=args.dry_run)
        total_ok += ok
        total_skip += skip
    print(f"\nsummary: reversed {total_ok}, skipped {total_skip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
