#!/usr/bin/env python3
"""Capture a read-only public data snapshot from a SuperNova backend.

This script performs only unauthenticated GET requests. It does not read the
database directly, write files, mutate data, run migrations, or delete media.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin


SNAPSHOT_PATHS = (
    "/health",
    "/supernova-status",
    "/proposals?filter=latest&limit=30",
)


def normalize_backend_url(value: str) -> str:
    clean = (value or "").strip().rstrip("/")
    if not clean:
        raise ValueError("backend URL is required")
    if not clean.startswith(("http://", "https://")):
        raise ValueError("backend URL must start with http:// or https://")
    return clean


def fetch_json(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    url = urljoin(f"{base_url}/", path.lstrip("/"))
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception as exc:  # pragma: no cover - defensive formatting
                body = None
                return {
                    "ok": False,
                    "status": getattr(response, "status", None),
                    "url": url,
                    "error": f"invalid JSON: {exc}",
                }
            return {
                "ok": 200 <= getattr(response, "status", 0) < 300,
                "status": getattr(response, "status", None),
                "url": url,
                "body": body,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "url": url, "error": str(exc)}
    except Exception as exc:
        return {"ok": False, "status": None, "url": url, "error": str(exc)}


def _append_media_url(values: list[str], value: Any) -> None:
    if isinstance(value, str):
        clean = value.strip()
        if clean and clean not in values:
            values.append(clean)
        return
    if isinstance(value, list):
        for item in value:
            _append_media_url(values, item)


def collect_media_urls(proposal: dict[str, Any]) -> list[str]:
    values: list[str] = []
    media = proposal.get("media")
    if isinstance(media, dict):
        for key in ("image", "images", "video", "file", "link", "created_image"):
            _append_media_url(values, media.get(key))
    for key in ("image", "images", "video", "file", "link", "created_image"):
        _append_media_url(values, proposal.get(key))
    return values


def proposal_summary(proposal: dict[str, Any]) -> dict[str, Any]:
    title = proposal.get("title") or proposal.get("text") or proposal.get("description") or ""
    return {
        "id": proposal.get("id"),
        "title": str(title).strip()[:120],
        "author": proposal.get("userName") or proposal.get("username") or proposal.get("author"),
        "media_urls": collect_media_urls(proposal),
    }


def build_snapshot(base_url: str, timeout: float) -> dict[str, Any]:
    endpoints = {path: fetch_json(base_url, path, timeout) for path in SNAPSHOT_PATHS}
    proposals_body = endpoints["/proposals?filter=latest&limit=30"].get("body")
    proposals = proposals_body if isinstance(proposals_body, list) else []
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "backend_url": base_url,
        "endpoints": {
            path: {
                "ok": result.get("ok"),
                "status": result.get("status"),
                "url": result.get("url"),
                **({"error": result.get("error")} if result.get("error") else {}),
            }
            for path, result in endpoints.items()
        },
        "proposal_sample": {
            "count": len(proposals),
            "items": [proposal_summary(item) for item in proposals if isinstance(item, dict)],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture a read-only public data snapshot.")
    parser.add_argument("backend_url", help="Backend base URL, for example http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=7.0, help="Request timeout in seconds")
    args = parser.parse_args(argv)

    try:
        base_url = normalize_backend_url(args.backend_url)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    snapshot = build_snapshot(base_url, args.timeout)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0 if all(endpoint["ok"] for endpoint in snapshot["endpoints"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
