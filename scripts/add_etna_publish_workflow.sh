#!/usr/bin/env bash
# Drop .github/workflows/etna-publish.yml into a Python workload fork and
# push. Mirrors the file alpaylan/strsim-etna ships, calling the reusable
# workflow at alpaylan/etna-cli@fix-canary-rollout (which now has a
# Python toolchain block as of commit eea9093).
#
# Idempotent — re-running is a no-op if the file is unchanged.
#
# Usage: scripts/add_etna_publish_workflow.sh <workload-dir-name>

set -euo pipefail

D=${1:?usage: $0 <workload-dir-name>}
ROOT=/Users/akeles/Programming/projects/PbtBenchmark/faultloc/workloads/Python/$D
[ -d "$ROOT" ] || { echo "no such workload: $ROOT" >&2; exit 2; }

cd "$ROOT"
echo "=== $D ==="

mkdir -p .github/workflows

cat > .github/workflows/etna-publish.yml <<'YAML'
name: Publish experiment results

on:
  push:
    branches: [main, master]
    paths-ignore:
      - '**.md'
      - '.github/**'
  workflow_dispatch:

permissions:
  contents: read
  deployments: write

jobs:
  publish:
    uses: alpaylan/etna-cli/.github/workflows/run-and-publish.yml@fix-canary-rollout
    with:
      trials: 10
      timeout: 60
    secrets:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
      CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
YAML

if git diff --quiet -- .github/workflows/etna-publish.yml \
   && [ -z "$(git status --porcelain -- .github/workflows/etna-publish.yml)" ]; then
  echo "  (no change)"
  exit 0
fi

git add .github/workflows/etna-publish.yml
git commit -m "ci: add etna-publish workflow (Hypothesis + CrossHair → CF Pages)" \
           -m "Calls the reusable workflow at alpaylan/etna-cli@fix-canary-rollout, which" \
           -m "now installs setup-python + uv when language == 'python'." \
           -m "Requires CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID secrets on this repo." \
           -m "Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"

branch=$(git rev-parse --abbrev-ref HEAD)
git push origin "$branch"
echo "  pushed to $branch"
