#!/bin/sh
# Pre-commit hook body for ETNA Haskell workload repos.
#
# Each workload's `.git/hooks/pre-commit` is a one-liner that execs this script:
#   #!/bin/sh
#   exec /Users/akeles/Programming/projects/PbtBenchmark/faultloc/scripts/workload_precommit_haskell.sh "$@"
#
# Runs three checks against the current working directory:
#   1. `etna workload check .` — manifest/docs drift (pinned etna version).
#   2. `python scripts/check_haskell_workload.py .` — Haskell-specific
#      manifest/source/patch consistency.
#   3. `cabal test etna-witnesses` — every committed witness must equal
#      Pass on the base tree (catches witnesses that broke under upstream
#      drift before the workload reaches the validate stage of an
#      etna-ify run).
set -eu

EXPECTED_ETNA_VERSION="etna 0.1.14"
FAULTLOC_ROOT="/Users/akeles/Programming/projects/PbtBenchmark/faultloc"

# 1. etna workload check (manifest + docs).
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

# `etna workload check` may not yet support language="haskell"; if it
# doesn't, fall through to the Python-based haskell checker which is the
# authoritative invariant gate for Haskell workloads.
if etna workload check . 2>/dev/null; then
  :
else
  echo "pre-commit: 'etna workload check' did not pass (may not yet support language=haskell). Continuing to scripts/check_haskell_workload.py — fix any Haskell-specific drift it reports below." >&2
fi

# 2. Haskell-specific consistency check.
if ! python3 "$FAULTLOC_ROOT/scripts/check_haskell_workload.py" . ; then
  echo "pre-commit: 'check_haskell_workload.py' reported drift — fix findings above (or regenerate docs with 'etna workload doc .') before committing." >&2
  exit 1
fi

# 3. Witness sanity. Skip if there is no etna-runner cabal package yet
#    (early during a workload's initial scaffolding) or if cabal is not
#    on PATH. Falsify needs base >= 4.18 = GHC >= 9.6, so we pin via
#    ghcup if available — otherwise let cabal use whatever's on PATH.
if [ -f etna/etna-runner.cabal ] && command -v cabal >/dev/null 2>&1; then
  ghc_arg=""
  if command -v ghcup >/dev/null 2>&1; then
    ghc_path="$(ghcup whereis ghc 9.6.6 2>/dev/null || true)"
    if [ -n "$ghc_path" ] && [ -x "$ghc_path" ]; then
      ghc_arg="--with-compiler=$ghc_path"
    fi
  fi
  if ! cabal $ghc_arg test etna-witnesses --test-show-details=failures >/dev/null 2>&1; then
    echo "pre-commit: 'cabal test etna-witnesses' failed — at least one witness does not return Pass on the base tree. Sharpen the witness or fix the underlying property before committing." >&2
    exit 1
  fi
fi
