#!/usr/bin/env bash
# flip_haskell_patches.sh — convert each Haskell workload's patches from
# reverse-apply (-R installs bug) to forward-apply (apply installs bug).
#
# Etna's driver runs `git apply <patch>` (no -R) for `kind = "patch"`
# variants. Our overnight pipeline initially generated patches in the
# wrong direction (`git diff -R`); this rewrites them in the right
# direction.
#
# Bug-fix vs prior version: stages all flipped patches in /tmp before
# moving any of them into place, so a multi-patch workload's later
# iterations don't cause `git checkout` to overwrite earlier-iteration
# flipped patch files. Also filters `git diff --name-only` to exclude
# patches/ when computing files to reset.
#
# Idempotent: if the patch already forward-applies (etna-compatible),
# skip.
set -u

FAULTLOC=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
TARGETS=${@:-$(ls -d "$FAULTLOC"/workloads/Haskell/*/ 2>/dev/null)}

flipped=0
skipped=0
errors=0

for d in $TARGETS; do
    [ -d "$d/patches" ] || continue
    name=$(basename "$d")
    cd "$d" || continue

    shopt -s nullglob
    patches=( patches/*.patch )
    shopt -u nullglob
    [ ${#patches[@]} -gt 0 ] || continue

    echo "[$name]"
    tmpdir=$(mktemp -d)

    # First pass: stage flipped patches into /tmp.
    for p in "${patches[@]}"; do
        base=$(basename "$p")
        if git apply --check --whitespace=nowarn "$p" 2>/dev/null; then
            echo "  ok already: $p"
            skipped=$((skipped + 1))
            continue
        fi
        if ! git apply --check -R --whitespace=nowarn "$p" 2>/dev/null; then
            echo "  ERROR: patch applies neither direction: $p" >&2
            errors=$((errors + 1))
            continue
        fi
        git apply -R --whitespace=nowarn "$p"
        git diff > "$tmpdir/$base"
        # Reset only source files (not patches/), so subsequent iters
        # work from clean base.
        files=$(git diff --name-only | grep -v '^patches/' || true)
        [ -n "$files" ] && git checkout -- $files
    done

    # Second pass: now that no source files are dirty, move staged
    # flipped patches into place. patches/<name>.patch was never
    # modified during the first pass, so this is the only mutation
    # to patches/.
    for p in "${patches[@]}"; do
        base=$(basename "$p")
        if [ -f "$tmpdir/$base" ]; then
            mv "$tmpdir/$base" "$p"
            if git apply --check --whitespace=nowarn "$p" 2>/dev/null; then
                echo "  flipped: $p"
                flipped=$((flipped + 1))
            else
                echo "  ERROR: flipped patch doesn't forward-apply: $p" >&2
                errors=$((errors + 1))
            fi
        fi
    done
    rm -rf "$tmpdir"
done

cd "$FAULTLOC"
echo "---"
echo "flipped: $flipped"
echo "already-ok: $skipped"
echo "errors: $errors"
