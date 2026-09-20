#!/usr/bin/env python3
"""Verify a pushed release tag equals platform.json's top-level "version".

Runs in .github/workflows/release.yml as the gate before a GitHub Release is
created; also runnable locally with the tag as argv[1] (or GITHUB_REF_NAME)
to rehearse a release without pushing anything.

This script is read-only, so it uses plain json.loads. Do not "harmonize" it
with the text-surgical parsing in update_framework_zephyr.py: that script
*writes* platform.json and must not re-serialize the hand-formatted file;
there is no write here to keep quiet.

Set PLATFORM_JSON to point at a scratch copy when testing the pass path
(sibling-script convention).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DEFAULT_PLATFORM_JSON = Path(__file__).resolve().parents[2] / "platform.json"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def main(argv: list[str]) -> int:
    tag = os.environ.get("GITHUB_REF_NAME") or (argv[0] if argv else "")
    if not tag:
        print("ERROR: pass the tag as argv[1] or set GITHUB_REF_NAME", file=sys.stderr)
        return 2

    if not SEMVER_RE.match(tag):
        print(
            f"ERROR: tag {tag!r} is not strict semver (X.Y.Z). Release tags carry "
            "no 'v' prefix; pre-release suffixes are not supported by this flow.",
            file=sys.stderr,
        )
        return 1

    platform_json = Path(os.environ.get("PLATFORM_JSON", str(DEFAULT_PLATFORM_JSON)))
    if not platform_json.exists():
        print(f"ERROR: platform.json not found at {platform_json}", file=sys.stderr)
        return 2

    data = json.loads(platform_json.read_text(encoding="utf-8"))
    platform_version = data.get("version")

    if platform_version != tag:
        print(
            f'ERROR: tag {tag!r} != platform.json "version" {platform_version!r}.\n'
            "Fix: bump the top-level \"version\" in platform.json on main to match "
            "the tag, then delete and re-push the tag from that commit.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: tag {tag} == platform.json version {platform_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
