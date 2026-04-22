#!/bin/sh
# Install the shared ETNA drift-gate pre-commit hook into every Rust workload
# repo under faultloc/workloads/Rust/ that is a real git repository with an
# etna.toml. Idempotent — existing hook bodies are overwritten, but any
# pre-existing non-hook files under .git/hooks/ are left alone.
set -eu

SHARED_HOOK="/Users/akeles/Programming/projects/PbtBenchmark/faultloc/scripts/workload_precommit.sh"
WORKLOADS_ROOT="/Users/akeles/Programming/projects/PbtBenchmark/faultloc/workloads/Rust"

[ -x "$SHARED_HOOK" ] || { echo "missing or non-executable: $SHARED_HOOK" >&2; exit 1; }

installed=0
skipped=0

for dir in "$WORKLOADS_ROOT"/*/ ; do
  [ -d "$dir" ] || continue
  workload="$(basename "$dir")"

  # Skip generator-style workloads (no etna.toml).
  if [ ! -f "$dir/etna.toml" ]; then
    echo "skip $workload (no etna.toml)"
    skipped=$((skipped + 1))
    continue
  fi

  # Skip dirs that aren't standalone git repos.
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
