#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_SCRIPT="${REPO_ROOT}/scripts/build_calcie_macos_app.sh"
APP_SOURCE="${REPO_ROOT}/dist/CALCIE.app"
APP_TARGET_DIR="${HOME}/Applications"
APP_TARGET="${APP_TARGET_DIR}/CALCIE.app"
OPEN_AFTER_INSTALL="${CALCIE_OPEN_AFTER_INSTALL:-1}"
APP_BUNDLE_ID="com.suryateja.calcie"

if [[ ! -x "${BUILD_SCRIPT}" ]]; then
  echo "Missing build script: ${BUILD_SCRIPT}" >&2
  exit 1
fi

echo "Preparing CALCIE.app bundle..."
"${BUILD_SCRIPT}"

if [[ ! -d "${APP_SOURCE}" ]]; then
  echo "Built app bundle not found at ${APP_SOURCE}" >&2
  exit 1
fi

echo "Closing any running CALCIE instance..."
osascript -e "tell application id \"${APP_BUNDLE_ID}\" to quit" >/dev/null 2>&1 || true
pkill -x "CALCIE" >/dev/null 2>&1 || true
for _ in {1..20}; do
  if ! pgrep -x "CALCIE" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

mkdir -p "${APP_TARGET_DIR}"
rm -rf "${APP_TARGET}"
ditto "${APP_SOURCE}" "${APP_TARGET}"

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "${APP_TARGET}" >/dev/null 2>&1 || true
fi

echo "Installed CALCIE.app to ${APP_TARGET}"
echo ""
echo "Next steps:"
echo "1. Open CALCIE.app from ~/Applications"
echo "2. Grant permissions to CALCIE.app when macOS prompts"
echo "3. If needed, review permissions in System Settings > Privacy & Security"
echo "4. If permissions keep resetting after reinstall, run ./scripts/check_calcie_codesign.sh"
echo "5. Then follow CALCIE_CODESIGN_SETUP.md to configure CALCIE_CODESIGN_IDENTITY with a stable Apple Development or Developer ID certificate before building."

if [[ "${OPEN_AFTER_INSTALL}" == "1" ]]; then
  echo ""
  echo "Launching CALCIE.app..."
  open "${APP_TARGET}"
fi
