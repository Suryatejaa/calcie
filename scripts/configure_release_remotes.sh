#!/bin/zsh
set -euo pipefail

DEV_URL="${CALCIE_DEV_REPO_URL:-https://github.com/Suryatejaa/calcie.git}"
PROD_URL="${CALCIE_PROD_REPO_URL:-https://github.com/EchoLift/calcie.git}"
WEBSITE_URL="${CALCIE_WEBSITE_REPO_URL:-https://github.com/EchoLift/calcie-official.git}"

set_remote() {
  local name="$1"
  local url="$2"
  if git remote get-url "$name" >/dev/null 2>&1; then
    git remote set-url "$name" "$url"
  else
    git remote add "$name" "$url"
  fi
}

# If origin is still the personal/dev repository, keep it available as `dev`.
if git remote get-url origin >/dev/null 2>&1; then
  ORIGIN_URL="$(git remote get-url origin)"
  if [[ "$ORIGIN_URL" == "$DEV_URL" ]] && ! git remote get-url dev >/dev/null 2>&1; then
    git remote rename origin dev
  fi
fi

set_remote dev "$DEV_URL"
set_remote prod "$PROD_URL"
set_remote website "$WEBSITE_URL"

cat <<EOF
Configured CALCIE release remotes:

$(git remote -v)

Dev flow:
  git push dev HEAD:main

Prod promotion:
  git push prod HEAD:prod

Website repo:
  use scripts/export_website.sh, then push that output to the website remote/repo.
EOF
