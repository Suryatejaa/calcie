#!/bin/zsh
set -euo pipefail

MODE="${1:-dry-run}"
DEV_REMOTE="${CALCIE_DEV_REMOTE:-dev}"
PROD_REMOTE="${CALCIE_PROD_REMOTE:-prod}"
DEV_BRANCH="${CALCIE_DEV_BRANCH:-main}"
PROD_BRANCH="${CALCIE_PROD_BRANCH:-prod}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree has uncommitted changes. Commit or stash before promotion." >&2
  git status --short
  exit 1
fi

echo "Running release hygiene..."
./scripts/check_release_hygiene.py

echo "Running Python syntax checks..."
PYTHONPYCACHEPREFIX=/tmp/calcie_pycache python3 -m py_compile \
  calcie.py \
  calcie_cloud/server.py \
  calcie_local_api/server.py \
  scripts/check_release_hygiene.py \
  scripts/publish_calcie_release.py

cat <<EOF
Promotion plan:
  1. Push current HEAD to dev:  ${DEV_REMOTE} HEAD:${DEV_BRANCH}
  2. Test dev deployment/manual QA
  3. Push same HEAD to prod:    ${PROD_REMOTE} HEAD:${PROD_BRANCH}
EOF

if [[ "$MODE" != "--execute" ]]; then
  echo "Dry run only. Re-run with --execute to push dev and prod branches."
  exit 0
fi

git push "$DEV_REMOTE" "HEAD:${DEV_BRANCH}"
echo "Dev push complete. Run manual QA before continuing."
echo "Type 'promote' to push to prod/${PROD_BRANCH}:"
read CONFIRM
if [[ "$CONFIRM" != "promote" ]]; then
  echo "Prod promotion cancelled."
  exit 0
fi

git push "$PROD_REMOTE" "HEAD:${PROD_BRANCH}"
echo "Prod promotion complete."
