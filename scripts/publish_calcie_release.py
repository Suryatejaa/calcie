#!/usr/bin/env python3
"""Publish a CALCIE release manifest to the cloud update endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "dist" / "calcie_release_manifest.json"


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Manifest not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Could not read manifest JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Manifest JSON must be an object.")
    return data


def validate_manifest(manifest: dict, allow_empty_url: bool = False) -> None:
    required = ["platform", "channel", "version", "build", "download_url", "sha256", "minimum_os"]
    missing = [key for key in required if key not in manifest]
    if missing:
        raise SystemExit(f"Manifest is missing required fields: {', '.join(missing)}")
    if not allow_empty_url and not str(manifest.get("download_url") or "").strip():
        raise SystemExit(
            "Manifest download_url is empty. Rebuild with CALCIE_RELEASE_PUBLIC_BASE_URL, "
            "or pass --download-url after uploading the DMG."
        )
    if not str(manifest.get("sha256") or "").strip():
        raise SystemExit("Manifest sha256 is empty.")


def post_manifest(base_url: str, manifest: dict, admin_token: str = "") -> dict:
    url = base_url.rstrip("/") + "/updates/releases"
    body = json.dumps(manifest).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    if admin_token:
        request.add_header("x-calcie-admin-token", admin_token)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8", errors="replace")
            return json.loads(text or "{}")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Publish failed with HTTP {exc.code}: {body_text}") from exc
    except Exception as exc:
        raise SystemExit(f"Publish failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to release manifest JSON")
    parser.add_argument("--cloud-url", default=os.environ.get("CALCIE_CLOUD_BASE_URL") or os.environ.get("CALCIE_SYNC_BASE_URL") or "https://calcie.onrender.com")
    parser.add_argument("--admin-token", default=os.environ.get("CALCIE_CLOUD_ADMIN_TOKEN", ""))
    parser.add_argument("--download-url", default="", help="Override manifest download_url")
    parser.add_argument("--release-notes-url", default="", help="Override manifest release_notes_url")
    parser.add_argument("--channel", default="", help="Override manifest channel")
    parser.add_argument("--required", action="store_true", help="Mark update as required")
    parser.add_argument("--dry-run", action="store_true", help="Print payload without publishing")
    parser.add_argument("--allow-empty-url", action="store_true", help="Allow empty download_url for local/dev dry-runs")
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest).resolve())
    if args.download_url:
        manifest["download_url"] = args.download_url
    if args.release_notes_url:
        manifest["release_notes_url"] = args.release_notes_url
    if args.channel:
        manifest["channel"] = args.channel
    if args.required:
        manifest["required"] = True

    validate_manifest(manifest, allow_empty_url=args.allow_empty_url or args.dry_run)

    print(json.dumps(manifest, indent=2, ensure_ascii=True))
    if args.dry_run:
        print("Dry run only. Release was not published.")
        return 0

    result = post_manifest(args.cloud_url, manifest, admin_token=args.admin_token)
    if not result.get("ok"):
        raise SystemExit(f"Publish returned non-ok response: {result}")
    print(f"Published release id {result.get('id')} to {args.cloud_url.rstrip('/')}/updates/releases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
