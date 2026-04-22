#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="${1:-${ROOT}/dist/calcie-official-site}"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

cp "$ROOT/index.html" "$OUT_DIR/index.html"
cp "$ROOT/styles.css" "$OUT_DIR/styles.css"
cp "$ROOT/main.js" "$OUT_DIR/main.js"
cp -R "$ROOT/docs" "$OUT_DIR/docs"
cp -R "$ROOT/releases" "$OUT_DIR/releases"

cat > "$OUT_DIR/vercel.json" <<'JSON'
{
  "cleanUrls": true,
  "trailingSlash": false
}
JSON

cat > "$OUT_DIR/README.md" <<'EOF'
# CALCIE Official Website

Static launch website for CALCIE.

Deploy target: Vercel.
EOF

find "$OUT_DIR" -type f -print
