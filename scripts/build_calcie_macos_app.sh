#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SWIFT_ROOT="${REPO_ROOT}/calcie_macos"
CONFIGURATION="${1:-debug}"
APP_NAME="CALCIE.app"
DIST_DIR="${REPO_ROOT}/dist"
APP_DIR="${DIST_DIR}/${APP_NAME}"
EXECUTABLE_SOURCE="${SWIFT_ROOT}/.build/${CONFIGURATION}/CalcieMenuBar"
EXECUTABLE_DEST="${APP_DIR}/Contents/MacOS/CALCIE"
RESOURCES_DIR="${APP_DIR}/Contents/Resources"
INFO_PLIST_SOURCE="${SWIFT_ROOT}/Bundle/Info.plist"
CONFIG_PATH="${RESOURCES_DIR}/calcie_app_config.json"
LOGO_SOURCE="${REPO_ROOT}/calcie-logo.png"
SIGN_IDENTITY="${CALCIE_CODESIGN_IDENTITY:-}"
SIGN_STYLE="ad-hoc"
BUILD_TIME_UTC="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
SIGN_IDENTITY_JSON="null"
CLOUD_BASE_URL="${CALCIE_CLOUD_BASE_URL:-${CALCIE_SYNC_BASE_URL:-https://calcie.onrender.com}}"
RELEASE_CHANNEL="${CALCIE_RELEASE_CHANNEL:-alpha}"
SHOW_DEVELOPER_TOOLS="${CALCIE_SHOW_DEVELOPER_TOOLS:-}"

if [[ ! -f "${INFO_PLIST_SOURCE}" ]]; then
  echo "Missing Info.plist template at ${INFO_PLIST_SOURCE}" >&2
  exit 1
fi

echo "Building CALCIE macOS shell (${CONFIGURATION})..."
(
  cd "${SWIFT_ROOT}"
  swift build -c "${CONFIGURATION}"
)

if [[ ! -x "${EXECUTABLE_SOURCE}" ]]; then
  echo "Expected executable not found at ${EXECUTABLE_SOURCE}" >&2
  exit 1
fi

rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}/Contents/MacOS" "${RESOURCES_DIR}"

cp "${INFO_PLIST_SOURCE}" "${APP_DIR}/Contents/Info.plist"
cp "${EXECUTABLE_SOURCE}" "${EXECUTABLE_DEST}"
chmod +x "${EXECUTABLE_DEST}"
if [[ -f "${LOGO_SOURCE}" ]]; then
  cp "${LOGO_SOURCE}" "${RESOURCES_DIR}/calcie-logo.png"
fi

if command -v codesign >/dev/null 2>&1; then
  if [[ -z "${SIGN_IDENTITY}" ]]; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F '"' '/Apple Development|Developer ID Application/ {print $2; exit}')"
  fi
  if [[ -n "${SIGN_IDENTITY}" ]]; then
    if codesign --force --deep --sign "${SIGN_IDENTITY}" "${APP_DIR}" >/dev/null 2>&1; then
      SIGN_STYLE="stable"
    else
      echo "Warning: failed to sign with identity '${SIGN_IDENTITY}'. Falling back to ad-hoc signing." >&2
      codesign --force --deep --sign - "${APP_DIR}" >/dev/null 2>&1 || true
    fi
  else
    codesign --force --deep --sign - "${APP_DIR}" >/dev/null 2>&1 || true
  fi
fi

if [[ -n "${SIGN_IDENTITY}" ]]; then
  SIGN_IDENTITY_JSON="\"${SIGN_IDENTITY//\"/\\\"}\""
fi

if [[ -z "${SHOW_DEVELOPER_TOOLS}" ]]; then
  if [[ "${CONFIGURATION:l}" == "release" ]]; then
    SHOW_DEVELOPER_TOOLS="false"
  else
    SHOW_DEVELOPER_TOOLS="true"
  fi
fi

cat > "${CONFIG_PATH}" <<JSON
{
  "project_root":"${REPO_ROOT}",
  "build_configuration":"${CONFIGURATION}",
  "code_signing_style":"${SIGN_STYLE}",
  "code_signing_identity":${SIGN_IDENTITY_JSON},
  "built_at":"${BUILD_TIME_UTC}",
  "repo_backed":true,
  "show_developer_tools":${SHOW_DEVELOPER_TOOLS},
  "cloud_base_url":"${CLOUD_BASE_URL}",
  "release_channel":"${RELEASE_CHANNEL}"
}
JSON

echo "Built app bundle: ${APP_DIR}"
echo "You can move it to ~/Applications or /Applications."
if [[ "${SIGN_STYLE}" == "stable" ]]; then
  echo "Code signing: stable identity (${SIGN_IDENTITY})"
else
  echo "Code signing: ad-hoc"
  echo "Note: macOS privacy permissions may reset after reinstall until CALCIE.app is signed with a stable identity."
  echo "Set CALCIE_CODESIGN_IDENTITY to an Apple Development or Developer ID Application certificate when available."
fi
