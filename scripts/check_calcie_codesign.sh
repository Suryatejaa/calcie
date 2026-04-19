#!/bin/zsh
set -euo pipefail

echo "Checking available macOS code-signing identities..."
echo ""

IDENTITIES="$(security find-identity -v -p codesigning 2>/dev/null || true)"

if [[ -z "${IDENTITIES}" ]]; then
  echo "No code-signing identities were returned by macOS."
  echo ""
  echo "Next steps:"
  echo "1. Open Xcode"
  echo "2. Go to Xcode > Settings > Accounts"
  echo "3. Sign in with your Apple ID"
  echo "4. Let Xcode create or download an Apple Development certificate"
  echo "5. Re-run this script"
  exit 0
fi

echo "${IDENTITIES}"
echo ""

MATCHING_IDENTITIES="$(printf '%s\n' "${IDENTITIES}" | awk -F '\"' '/Apple Development|Developer ID Application/ {print $2}')"

if [[ -n "${MATCHING_IDENTITIES}" ]]; then
  echo "Usable signing identities for CALCIE:"
  printf ' - %s\n' ${(f)MATCHING_IDENTITIES}
  echo ""
  FIRST_IDENTITY="$(printf '%s\n' "${MATCHING_IDENTITIES}" | head -n 1)"
  echo "Recommended next commands:"
  echo "export CALCIE_CODESIGN_IDENTITY=\"${FIRST_IDENTITY}\""
  echo "./scripts/install_calcie_macos_app.sh"
else
  echo "macOS returned identities, but none match Apple Development or Developer ID Application."
  echo ""
  echo "Next steps:"
  echo "1. Open Xcode > Settings > Accounts"
  echo "2. Select your Apple ID team"
  echo "3. Open Manage Certificates..."
  echo "4. Create an Apple Development certificate"
  echo "5. Re-run this script"
fi
