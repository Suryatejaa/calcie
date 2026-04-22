#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_SCRIPT="${REPO_ROOT}/scripts/build_calcie_macos_app.sh"
HYGIENE_SCRIPT="${REPO_ROOT}/scripts/check_release_hygiene.py"
INFO_PLIST="${REPO_ROOT}/calcie_macos/Bundle/Info.plist"
DIST_DIR="${REPO_ROOT}/dist"
APP_PATH="${DIST_DIR}/CALCIE.app"
DMG_STAGE="${DIST_DIR}/dmg_stage"
METADATA_PATH="${DIST_DIR}/calcie_release_manifest.json"
CONFIGURATION="${1:-release}"
RELEASE_CHANNEL="${CALCIE_RELEASE_CHANNEL:-alpha}"
PUBLIC_BASE_URL="${CALCIE_RELEASE_PUBLIC_BASE_URL:-}"
DMG_SIGN_IDENTITY="${CALCIE_DMG_CODESIGN_IDENTITY:-${CALCIE_CODESIGN_IDENTITY:-}}"

if [[ ! -x "${BUILD_SCRIPT}" ]]; then
  echo "Missing build script: ${BUILD_SCRIPT}" >&2
  exit 1
fi

if [[ ! -x "${HYGIENE_SCRIPT}" ]]; then
  echo "Missing release hygiene script: ${HYGIENE_SCRIPT}" >&2
  exit 1
fi

VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "${INFO_PLIST}")"
BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "${INFO_PLIST}")"
DMG_NAME="CALCIE-${VERSION}-${BUILD}-${RELEASE_CHANNEL}.dmg"
DMG_PATH="${DIST_DIR}/${DMG_NAME}"
VOLUME_NAME="CALCIE ${VERSION}"

cd "${REPO_ROOT}"

echo "Running release hygiene check..."
"${HYGIENE_SCRIPT}"

echo "Building CALCIE.app (${CONFIGURATION})..."
"${BUILD_SCRIPT}" "${CONFIGURATION}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "Built app not found: ${APP_PATH}" >&2
  exit 1
fi

rm -rf "${DMG_STAGE}" "${DMG_PATH}"
mkdir -p "${DMG_STAGE}"

cp -R "${APP_PATH}" "${DMG_STAGE}/CALCIE.app"
ln -s /Applications "${DMG_STAGE}/Applications"
cat > "${DMG_STAGE}/README.txt" <<EOF
CALCIE ${VERSION} (${BUILD})

Drag CALCIE.app into Applications, then open it from Applications.
Grant microphone, accessibility, screen recording, and notification permissions when prompted.
EOF

echo "Creating DMG: ${DMG_PATH}"
hdiutil create \
  -volname "${VOLUME_NAME}" \
  -srcfolder "${DMG_STAGE}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

if [[ -n "${DMG_SIGN_IDENTITY}" ]] && command -v codesign >/dev/null 2>&1; then
  echo "Signing DMG with ${DMG_SIGN_IDENTITY}..."
  codesign --force --sign "${DMG_SIGN_IDENTITY}" "${DMG_PATH}"
else
  echo "DMG signing skipped. Set CALCIE_DMG_CODESIGN_IDENTITY or CALCIE_CODESIGN_IDENTITY to sign."
fi

SHA256="$(shasum -a 256 "${DMG_PATH}" | awk '{print $1}')"
DOWNLOAD_URL="${PUBLIC_BASE_URL%/}/${DMG_NAME}"
if [[ -z "${PUBLIC_BASE_URL}" ]]; then
  DOWNLOAD_URL=""
fi

cat > "${METADATA_PATH}" <<JSON
{
  "platform": "macos",
  "channel": "${RELEASE_CHANNEL}",
  "version": "${VERSION}",
  "build": "${BUILD}",
  "download_url": "${DOWNLOAD_URL}",
  "sha256": "${SHA256}",
  "release_notes_url": "${CALCIE_RELEASE_NOTES_URL:-}",
  "minimum_os": "13.0",
  "required": false,
  "metadata": {
    "dmg_name": "${DMG_NAME}",
    "created_by": "scripts/build_calcie_dmg.sh"
  }
}
JSON

rm -rf "${DMG_STAGE}"

echo "Built DMG: ${DMG_PATH}"
echo "SHA256: ${SHA256}"
echo "Release metadata: ${METADATA_PATH}"
if [[ -z "${PUBLIC_BASE_URL}" ]]; then
  echo "Set CALCIE_RELEASE_PUBLIC_BASE_URL before release to populate download_url in metadata."
fi
