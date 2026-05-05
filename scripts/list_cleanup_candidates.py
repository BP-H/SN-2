#!/usr/bin/env python3
"""Print tracked cleanup candidates without deleting anything.

This is an inventory helper for future branch-tested cleanup. It only reads the
git index and prints paths that look generated, duplicated, legacy, or typoed.
"""

from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LEGACY_FRONTEND_DIRS = {
    "super-nova-2177/frontend-vite-basic",
}

LOCAL_DOCKER_COMPOSE_PATHS = {
    "super-nova-2177/docker-compose.yml",
    "super-nova-2177/backend/supernova_2177_ui_weighted/docker-compose.yml",
    "super-nova-2177/backend/supernova_2177_ui_weighted/backend/docker-compose.yml",
}

TRACKED_ARTIFACT_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
}

LOCAL_STORE_NAMES = {
    "messages_store.json",
    "follows_store.json",
}


def git_ls_files() -> list[str]:
    command = [
        "git",
        "-c",
        f"safe.directory={ROOT.as_posix()}",
        "ls-files",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr.strip() or "git ls-files failed", file=sys.stderr)
        raise SystemExit(result.returncode)
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def add_once(candidates: dict[str, set[str]], category: str, path: str) -> None:
    candidates[category].add(path)


def classify(paths: list[str]) -> dict[str, list[str]]:
    candidates: dict[str, set[str]] = defaultdict(set)

    for path in paths:
        lower_path = path.lower()
        name = Path(path).name.lower()
        suffix = Path(path).suffix.lower()

        if name == "combined_repo.md":
            add_once(candidates, "combined repo snapshots", path)

        if suffix in TRACKED_ARTIFACT_SUFFIXES:
            add_once(candidates, "tracked generated/local artifacts", path)

        if name in LOCAL_STORE_NAMES:
            add_once(candidates, "tracked local JSON stores", path)

        if name.endswith(".bak") or ".backup" in name or name.startswith("backup-"):
            add_once(candidates, "backup-looking tracked files", path)

        if "/uploads/" in lower_path or lower_path.endswith("/uploads"):
            add_once(candidates, "tracked uploads", path)

        if any(lower_path.startswith(frontend_dir + "/") for frontend_dir in LEGACY_FRONTEND_DIRS):
            frontend_root = "/".join(path.split("/")[:2])
            add_once(candidates, "legacy or experimental frontend trees", frontend_root)

        if path in LOCAL_DOCKER_COMPOSE_PATHS:
            add_once(candidates, "local docker compose configs", path)

        if lower_path.startswith("super-nova-2177/backend/supernova_2177_ui_weighted/backend/"):
            add_once(candidates, "nested backend experiments", path)

        if name == "package-lock.json" and (
            lower_path.startswith("super-nova-2177/backend/")
            or "/supernova_2177_ui_weighted/" in lower_path
        ):
            add_once(candidates, "node lockfiles inside backend/module trees", path)

        if "animate_gaussion" in lower_path or "likesdeslikes" in lower_path:
            add_once(candidates, "typo-named tracked files", path)

    return {category: sorted(values) for category, values in sorted(candidates.items())}


def main() -> int:
    candidates = classify(git_ls_files())
    print("Tracked cleanup candidate inventory")
    print("Mode: read-only; no files are deleted or modified.\n")

    if not candidates:
        print("No cleanup candidates matched the current inventory rules.")
        return 0

    for category, paths in candidates.items():
        print(f"## {category} ({len(paths)})")
        for path in paths:
            print(f"- {path}")
        print()

    print("Review these on a separate cleanup branch before deleting anything.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
