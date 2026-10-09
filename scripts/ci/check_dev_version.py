#!/usr/bin/env python3
"""Verify dev's platform.json "version" is the *next* release, not a stale one.

Runs in .github/workflows/check-dev-version.yml on every push to dev. The
branch model it enforces (the publishing side lives in
release-on-merge.yml):

  * dev is the integration branch: all PRs target it, and its top-level
    "version" always names the release being built toward (e.g. 1.1.0).
  * main is the stable branch: a dev -> main merge is the only way a
    version ships (release-on-merge.yml checks the version on the PR and
    cuts the X.Y.Z tag on the merge commit).
  * After a release ships, the very next dev push fails here until "version"
    is bumped past the new tag -- that stall is intentional; bump dev to the
    next version (1.2.0, or 1.1.1 after a hotfix series) before merging more.
  * A hotfix released straight from main (say 1.0.1 while dev carries 1.1.0)
    needs no action: 1.1.0 > 1.0.1 still holds.

Like check_merge_version.py, this is read-only and runnable locally:
set PLATFORM_JSON to point at a scratch copy to rehearse the failure paths.

Set GIT_TAG_LIST to a newline-separated stand-in tag list to rehearse
against tags that only exist on the remote (sibling-script convention).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_PLATFORM_JSON = Path(__file__).resolve().parents[2] / "platform.json"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def released_tags() -> list[str]:
    """All strict-semver tags reachable from the local clone."""
    raw = os.environ.get("GIT_TAG_LIST")
    if raw is not None:
        return [line.strip() for line in raw.splitlines() if SEMVER_RE.match(line.strip())]
    out = subprocess.run(
        ["git", "tag", "--list"], capture_output=True, text=True, check=True
    ).stdout
    return [line.strip() for line in out.splitlines() if SEMVER_RE.match(line.strip())]


def as_tuple(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def main(argv: list[str]) -> int:
    platform_json = Path(os.environ.get("PLATFORM_JSON", str(DEFAULT_PLATFORM_JSON)))
    if not platform_json.exists():
        print(f"ERROR: platform.json not found at {platform_json}", file=sys.stderr)
        return 2

    data = json.loads(platform_json.read_text(encoding="utf-8"))
    version = data.get("version")

    if not isinstance(version, str) or not SEMVER_RE.match(version):
        print(
            f'ERROR: dev platform.json "version" {version!r} is not strict semver (X.Y.Z).\n'
            "dev carries the *next* release version; pre-release suffixes are not "
            "part of this flow (release-on-merge.yml only ever cuts plain X.Y.Z tags).",
            file=sys.stderr,
        )
        return 1

    tags = released_tags()
    if not tags:
        # Nothing released yet (fresh repository); any valid semver is fine.
        print(f"OK: no released tags exist yet; dev version {version} stands")
        return 0

    latest = max(tags, key=as_tuple)
    if as_tuple(version) > as_tuple(latest):
        print(f"OK: dev version {version} is past the latest released tag {latest}")
        return 0

    print(
        f'ERROR: dev platform.json "version" {version} must be strictly greater than '
        f"the latest released tag {latest}.\n"
        "If a release just shipped, bump \"version\" on dev to the next one before "
        "merging more; a stale version would make dev's unreleased commits install "
        "under the name of an existing release.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
