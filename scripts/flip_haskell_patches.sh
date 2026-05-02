#!/usr/bin/env bash
# flip_haskell_patches.sh — convert each Haskell workload's patches from
# reverse-apply (--R installs bug) to forward-apply (apply installs bug).
#
# Etna's driver runs `git apply <patch>` (no -R) for `kind = "patch"`
# variants. Our overnight pipeline initially generated patches in the
# wrong direction (`git diff -R`); this rewrites them in the right
# direction.
#
# Idempotent: if the forward-direction patch already applies cleanly
# (i.e. the file isn't currently in the buggy state and the patch's
# `---` side matches the working tree), skip.
#
# Per-workload steps:
#   for each patches/*.patch:
#     1. git apply -R <patch>   (install bug)
#     2. git diff > <patch>.new (forward diff: fixed → buggy)
#     3. git checkout <files>   (restore fixed state)
#     4. mv <patch>.new <patch>
#     5. git apply --check <patch>  (verify forward applies)
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

    # Quick check: skip workloads with no patches.
    shopt -s nullglob
    patches=( patches/*.patch )
    shopt -u nullglob
    [ ${#patches[@]} -gt 0 ] || continue

    echo "[$name]"
    for p in "${patches[@]}"; do
        # Try reverse-apply first to detect direction.
        if git apply --check -R --whitespace=nowarn "$p" 2>/dev/null; then
            # Reverse-applies cleanly → currently in old (wrong) direction.
            git apply -R --whitespace=nowarn "$p"
            git diff > "$p.new"
            # Reset working tree to base by reverse-applying the new (forward) patch.
            git checkout -- $(git diff --name-only)
            mv "$p.new" "$p"
            if git apply --check --whitespace=nowarn "$p" 2>/dev/null; then
                echo "  flipped: $p"
                flipped=$((flipped + 1))
            else
                echo "  ERROR: flipped patch doesn't forward-apply: $p" >&2
                errors=$((errors + 1))
            fi
        elif git apply --check --whitespace=nowarn "$p" 2>/dev/null; then
            # Already forward-direction (etna-compatible).
            echo "  ok already: $p"
            skipped=$((skipped + 1))
        else
            echo "  ERROR: patch applies neither direction: $p" >&2
            errors=$((errors + 1))
        fi
    done
done

cd "$FAULTLOC"
echo "---"
echo "flipped: $flipped"
echo "already-ok: $skipped"
echo "errors: $errors"
