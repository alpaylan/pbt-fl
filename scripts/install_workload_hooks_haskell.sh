#!/bin/sh
# Install the Haskell pre-commit hook into every Haskell workload repo
# under faultloc/workloads/Haskell/ that is a real git repository with
# an etna.toml. Idempotent — existing hook bodies are overwritten, but
# any pre-existing non-hook files under .git/hooks/ are left alone.
set -eu

SHARED_HOOK="/Users/akeles/Programming/projects/PbtBenchmark/faultloc/scripts/workload_precommit_haskell.sh"
WORKLOADS_ROOT="/Users/akeles/Programming/projects/PbtBenchmark/faultloc/workloads/Haskell"

[ -x "$SHARED_HOOK" ] || { echo "missing or non-executable: $SHARED_HOOK" >&2; exit 1; }

installed=0
skipped=0

for dir in "$WORKLOADS_ROOT"/*/ ; do
  [ -d "$dir" ] || continue
  workload="$(basename "$dir")"

  if [ ! -f "$dir/etna.toml" ]; then
    echo "skip $workload (no etna.toml)"
    skipped=$((skipped + 1))
    continue
  fi

  if [ ! -d "$dir/.git" ]; then
    echo "skip $workload (not a standalone git repo)"
    skipped=$((skipped + 1))
    continue
  fi

  hook="$dir/.git/hooks/pre-commit"
  cat > "$hook" <<EOF
#!/bin/sh
exec "$SHARED_HOOK" "\$@"
EOF
  chmod +x "$hook"
  echo "installed $workload"
  installed=$((installed + 1))
done

echo "---"
echo "installed: $installed"
echo "skipped:   $skipped"
