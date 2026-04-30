#!/bin/bash
# Bootstrap a Cedar-Lean workload tree at workloads/Lean/Cedar and print the
# command to launch the etna-ify agent against it.
#
# Idempotent — re-running on an existing workdir resumes from progress.jsonl
# without clobbering generated state.

set -euo pipefail

ROOT=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
WORKLOAD_DIR="$ROOT/workloads/Lean/Cedar"
CEDAR_SPEC_REPO_URL="https://github.com/cedar-policy/cedar-spec.git"
PROMPT_PATH="$ROOT/etna-ify/prompts/run-cedar.md"

usage() {
  cat <<EOF
Usage: $(basename "$0") [--base-commit <sha>] [--workdir <path>] [--launch*]

Sets up a Cedar-Lean ETNA workload by:
  1. Cloning cedar-spec (the Lean formalization) into the workdir
  2. Initializing an empty etna.toml + progress.jsonl
  3. Printing the agent invocation command (or executing it, with --launch*)

The agent is responsible for everything else: discovering bug-fix commits in
cedar-spec history, generating patches via 'git format-patch', writing
properties + witnesses, wiring the runner, and validating end-to-end. No
example variants are pre-seeded (giving the agent named bugs to chase tends
to bias it onto exactly those, leaving the rest of history un-mined).

Options:
  --base-commit <sha>     Pin the cedar-spec base commit (default: master HEAD)
  --workdir <path>        Workload directory (default: $WORKLOAD_DIR)
  --launch                After bootstrap, exec 'claude -p' headless with the
                          substituted prompt and --dangerously-skip-permissions
                          (required because -p cannot answer permission
                          prompts; without it the agent exits silently on the
                          first tool call).
  --launch-stream         Same as --launch but with --output-format stream-json
                          --verbose so you see each tool use / message in real
                          time instead of waiting for the final response.
  --launch-interactive    After bootstrap, exec 'claude' interactive (no -p) so
                          you can watch and answer permission prompts yourself
                          — recommended for the first run.
  -h, --help              Show this help

After bootstrap, the script prints copy-pasteable one-liners, or pass one of
the --launch* flags to invoke claude directly.
EOF
}

BASE_COMMIT=""
LAUNCH=0
LAUNCH_INTERACTIVE=0
LAUNCH_STREAM=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base-commit)         BASE_COMMIT="$2"; shift 2 ;;
    --workdir)             WORKLOAD_DIR="$2"; shift 2 ;;
    --launch)              LAUNCH=1; shift ;;
    --launch-interactive)  LAUNCH_INTERACTIVE=1; shift ;;
    --launch-stream)       LAUNCH=1; LAUNCH_STREAM=1; shift ;;
    -h|--help)             usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

mkdir -p "$(dirname "$WORKLOAD_DIR")"

# 1. Clone or refresh cedar-spec into a sibling cache, then sparse-checkout
#    cedar-lean/ + cedar-drt + cedar-lean-cli into the workdir.
SPEC_CACHE="$ROOT/.cache/cedar-spec"
if [ ! -d "$SPEC_CACHE/.git" ]; then
  echo "[etnaify_cedar] cloning cedar-spec into $SPEC_CACHE ..."
  mkdir -p "$(dirname "$SPEC_CACHE")"
  git clone --no-checkout "$CEDAR_SPEC_REPO_URL" "$SPEC_CACHE"
fi
(cd "$SPEC_CACHE" && git fetch --all --tags --prune)

if [ -z "$BASE_COMMIT" ]; then
  BASE_COMMIT=$(cd "$SPEC_CACHE" && git rev-parse origin/main)
fi
echo "[etnaify_cedar] cedar-spec base commit: $BASE_COMMIT"

if [ ! -d "$WORKLOAD_DIR/.cedar-spec/.git" ]; then
  echo "[etnaify_cedar] initializing $WORKLOAD_DIR from cedar-lean/ at $BASE_COMMIT ..."
  rm -rf "$WORKLOAD_DIR"
  mkdir -p "$WORKLOAD_DIR"
  git clone --no-checkout "$SPEC_CACHE" "$WORKLOAD_DIR/.cedar-spec"
  (cd "$WORKLOAD_DIR/.cedar-spec" && \
    git sparse-checkout init --cone && \
    git sparse-checkout set cedar-lean cedar-drt cedar-lean-cli && \
    git checkout "$BASE_COMMIT")
  # Surface the cedar-lean/ subtree at the workdir root so the agent's $1 is
  # the canonical workload path.
  ln -sfn .cedar-spec/cedar-lean/Cedar              "$WORKLOAD_DIR/Cedar"
  ln -sfn .cedar-spec/cedar-lean/lakefile.lean      "$WORKLOAD_DIR/lakefile.lean"
  ln -sfn .cedar-spec/cedar-lean/lean-toolchain     "$WORKLOAD_DIR/lean-toolchain"
  ln -sfn .cedar-spec/cedar-lean/lake-manifest.json "$WORKLOAD_DIR/lake-manifest.json" 2>/dev/null || true
  ln -sfn .cedar-spec/cedar-lean/README.md          "$WORKLOAD_DIR/CEDAR_README.md"
  ln -sfn .cedar-spec/cedar-drt                     "$WORKLOAD_DIR/cedar-drt"
  ln -sfn .cedar-spec/cedar-lean-cli                "$WORKLOAD_DIR/cedar-lean-cli"
fi

# 2. Skeleton files: empty etna.toml + progress.jsonl + patches/.
mkdir -p "$WORKLOAD_DIR/patches"
if [ ! -f "$WORKLOAD_DIR/etna.toml" ]; then
  cat > "$WORKLOAD_DIR/etna.toml" <<TOML
name = "cedar-lean"
description = """
ETNA workload for the Cedar-Lean formalization (cedar-policy/cedar-spec).
Each variant reintroduces one historical bug fix by reverse-applying a patch
against a fixed base commit and pairs it with a Plausible-driven property
and a deterministic witness. Patches are the only durable per-variant artefact;
no etna/<variant> git branches are used.
"""
language = "lean"
crate = "Cedar"
base_commit = "$BASE_COMMIT"

# [[tasks]] groups appended by the etna-ify atomize stage.
TOML
fi

if [ ! -f "$WORKLOAD_DIR/progress.jsonl" ]; then
  printf '{"ts":"%s","stage":"bootstrap","event":"workdir_ready","base_commit":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$BASE_COMMIT" \
    > "$WORKLOAD_DIR/progress.jsonl"
fi

# 3. Sanity checks
echo "[etnaify_cedar] sanity checks ..."
command -v lake >/dev/null 2>&1 || \
  echo "  WARNING: 'lake' not on PATH — install elan (https://leanprover.github.io/lean4/doc/setup.html) before running the agent."
[ -e "$WORKLOAD_DIR/lakefile.lean" ] || \
  { echo "  ERROR: lakefile.lean missing in $WORKLOAD_DIR" >&2; exit 1; }

# 4. Compose the substituted prompt (replace $1 / $@ with the workdir) and
#    either print one-liners or, with --launch*, invoke claude now.
SUBSTITUTED_PROMPT=$(sed -e "s|\\\$1|$WORKLOAD_DIR|g" -e "s|\\\$@|$WORKLOAD_DIR|g" "$PROMPT_PATH")

cat <<EOF

[etnaify_cedar] ready.
  workdir:                 $WORKLOAD_DIR
  cedar-spec base commit:  $BASE_COMMIT
  prompt:                  $PROMPT_PATH
  progress:                $WORKLOAD_DIR/progress.jsonl

etna.toml is empty (no [[tasks]] groups) — the agent populates it during
atomize from cedar-spec git history.

To launch (headless, fire-and-forget):
  claude -p --add-dir '$WORKLOAD_DIR' --dangerously-skip-permissions -- \\
    "\$(sed -e 's|\\\$1|$WORKLOAD_DIR|g' -e 's|\\\$@|$WORKLOAD_DIR|g' '$PROMPT_PATH')"
  # The '--' before the prompt is required: the prompt starts with YAML
  # frontmatter (---description: ...) which claude's CLI parser otherwise
  # treats as an unknown option. --dangerously-skip-permissions is also
  # required for -p; without it the agent exits silently on the first tool
  # call. Tail $WORKLOAD_DIR/progress.jsonl in another terminal to follow.

To launch (headless + stream tool events as they happen):
  claude -p --output-format stream-json --verbose \\
    --add-dir '$WORKLOAD_DIR' --dangerously-skip-permissions -- \\
    "\$(sed -e 's|\\\$1|$WORKLOAD_DIR|g' -e 's|\\\$@|$WORKLOAD_DIR|g' '$PROMPT_PATH')"

To launch (interactive — recommended for the first run so you can watch and
interrupt):
  claude --add-dir '$WORKLOAD_DIR' -- \\
    "\$(sed -e 's|\\\$1|$WORKLOAD_DIR|g' -e 's|\\\$@|$WORKLOAD_DIR|g' '$PROMPT_PATH')"

Or rerun this script with one of:
  --launch              headless one-shot (waits for final response)
  --launch-stream       headless with streaming JSON events
  --launch-interactive  interactive (you answer permission prompts)

To resume a partial run, just re-launch — the agent reads the tail of
progress.jsonl to pick up at the next incomplete stage.
EOF

if [ "$LAUNCH" -eq 1 ] || [ "$LAUNCH_INTERACTIVE" -eq 1 ]; then
  command -v claude >/dev/null 2>&1 || { echo "ERROR: 'claude' not on PATH" >&2; exit 1; }
  echo
  # NOTE: '--' before the prompt is REQUIRED. The prompt starts with YAML
  # frontmatter '---description: ...' which claude's CLI parser otherwise
  # treats as an unknown option and exits with 'error: unknown option'.
  if [ "$LAUNCH_INTERACTIVE" -eq 1 ]; then
    echo "[etnaify_cedar] launching interactive claude ..."
    exec claude --add-dir "$WORKLOAD_DIR" -- "$SUBSTITUTED_PROMPT"
  elif [ "$LAUNCH_STREAM" -eq 1 ]; then
    echo "[etnaify_cedar] launching: claude -p --output-format stream-json (streaming) ..."
    exec claude -p --output-format stream-json --verbose \
      --add-dir "$WORKLOAD_DIR" --dangerously-skip-permissions -- "$SUBSTITUTED_PROMPT"
  else
    echo "[etnaify_cedar] launching: claude -p headless (final-response only) ..."
    echo "[etnaify_cedar] tail $WORKLOAD_DIR/progress.jsonl in another terminal to follow progress."
    exec claude -p --add-dir "$WORKLOAD_DIR" --dangerously-skip-permissions -- "$SUBSTITUTED_PROMPT"
  fi
fi
