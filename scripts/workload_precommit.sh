#!/bin/sh
# Shared pre-commit hook body for ETNA workload repos.
#
# Each workload's `.git/hooks/pre-commit` is a one-liner that execs this script:
#   #!/bin/sh
#   exec /Users/akeles/Programming/projects/PbtBenchmark/faultloc/scripts/workload_precommit.sh "$@"
#
# The hook runs `etna workload check .` against the current working directory
# and fails on non-zero exit. A stale `etna` binary that doesn't understand the
# v2 schema could silently pass by rejecting the file, so we pin the version.
set -eu

EXPECTED_ETNA_VERSION="etna 0.1.7"

if ! command -v etna >/dev/null 2>&1; then
  echo "pre-commit: 'etna' CLI not on PATH; install etna-cli from /Users/akeles/Programming/projects/PbtBenchmark/etna2 first." >&2
  exit 1
fi

actual_version="$(etna --version 2>/dev/null | head -n1)"
if [ "$actual_version" != "$EXPECTED_ETNA_VERSION" ]; then
  echo "pre-commit: etna version mismatch — expected '$EXPECTED_ETNA_VERSION', got '$actual_version'." >&2
  echo "            rebuild etna-cli: cd /Users/akeles/Programming/projects/PbtBenchmark/etna2 && cargo install --path . --force" >&2
  exit 1
fi

if ! etna workload check . ; then
  echo "pre-commit: 'etna workload check' reported drift — fix findings above (or regenerate docs with 'etna workload doc .') before committing." >&2
  exit 1
fi
