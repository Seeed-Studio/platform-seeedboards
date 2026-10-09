#!/usr/bin/env python3
"""Verify platform.json "version" names an unreleased, forward version.

Runs in .github/workflows/release-on-merge.yml at two moments: on PRs into
main (pre-merge, so the red X shows before anyone reaches the merge button)
and on push to main (the gate right before CI cuts the tag).

This replaces the equality check the old release.yml performed at tag-push
time. The tag is now cut by CI from main's merge commit, so "tag == version"
and "tag on main" hold by construction; what still needs proving is that the
version being shipped is *new*:

  * strict X.Y.Z (the flow never emits anything else);
  * not an existing tag -- equality means the previous release shipped
    without dev's "version" being bumped past it (check-dev-version.yml
    exists to catch that earlier, on every dev push);
  * strictly greater than every existing tag -- lower means going backwards.

Like check_dev_version.py, this is read-only and rehearsable locally with
PLATFORM_JSON / GIT_TAG_LIST stand-ins (sibling-script convention).
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
    """All strict-semver tags visible to this clone."""
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
            f'ERROR: platform.json "version" {version!r} is not strict semver (X.Y.Z).',
            file=sys.stderr,
        )
        return 1

    tags = released_tags()
    if not tags:
        # Nothing released yet (fresh repository); any valid semver ships.
        print(f"OK: no released tags exist yet; {version} would be the first")
        return 0

    if version in tags:
        print(
            f'ERROR: platform.json "version" {version} names a tag that already exists.\n'
            "A dev -> main merge publishes a version, so the version being merged must be "
            "new. This usually means the previous release shipped without dev's "
            '"version" being bumped -- bump it on dev, then merge that through.',
            file=sys.stderr,
        )
        return 1

    latest = max(tags, key=as_tuple)
    if as_tuple(version) > as_tuple(latest):
        print(f"OK: {version} is unreleased and past the latest tag {latest}")
        return 0

    print(
        f'ERROR: platform.json "version" {version} is behind the latest released tag '
        f"{latest}; versions never go backwards. Bump \"version\" on dev past {latest} "
        "before merging to main.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
