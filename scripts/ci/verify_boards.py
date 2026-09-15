#!/usr/bin/env python3
"""Offline integrity gate for board manifests under boards/.

Fast, standalone, and package-cache-free (mirrors the invariant-gate pattern
from .agents/notes/proposed/2026-08-17-ai-workflow-adaptation.md). Run from
anywhere:

    python scripts/ci/verify_boards.py

Checks:
  1. every boards/*.json parses and carries the fields PlatformIO core
     requires (name, url, vendor) -- the exact class of corruption that
     would crash `pio boards` listing;
  2. the top-level `frameworks` list is non-empty and only names frameworks
     declared by platform.json;
  3. the set of board ids equals the conscious SUPPORTED_BOARD_IDS snapshot
     below -- additions/removals must be deliberate edits of this list;
  4. `build.zephyr`, when present, is an object (dict).

Exit code 0 = all checks pass, 1 = any violation (each reported by file).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_TOP_LEVEL_FIELDS = ("name", "url", "vendor")

# Conscious snapshot of the supported board ids (file stems under boards/).
# Adding or removing a board intentionally means updating this list; the
# failure message from check 3 explains that. Keep sorted.
SUPPORTED_BOARD_IDS = (
    "seeed-xiao-afruitnrf52-nrf52840",
    "seeed-xiao-afruitnrf52-nrf52840-plus",
    "seeed-xiao-afruitnrf52-nrf52840-sense",
    "seeed-xiao-afruitnrf52-nrf52840-sense-plus",
    "seeed-xiao-esp32-c3",
    "seeed-xiao-esp32-c5",
    "seeed-xiao-esp32-c6",
    "seeed-xiao-esp32-s3-plus",
    "seeed-xiao-esp32-s3-sense",
    "seeed-xiao-mbed-nrf52840",
    "seeed-xiao-mbed-nrf52840-plus",
    "seeed-xiao-mbed-nrf52840-sense",
    "seeed-xiao-mbed-nrf52840-sense-plus",
    "seeed-xiao-mg24",
    "seeed-xiao-mg24-sense",
    "seeed-xiao-nrf54l15",
    "seeed-xiao-nrf54lm20a",
    "seeed-xiao-nrf54lm20b",
    "seeed-xiao-ra4m1",
    "seeed-xiao-rp2040",
    "seeed-xiao-rp2350",
    "seeed-xiao-samd",
    "seeed-xiao-stm32c5",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_platform_frameworks(platform_json: Path) -> set:
    """Framework names declared by platform.json (empty set on failure)."""
    try:
        with platform_json.open("r", encoding="utf-8") as fp:
            return set(json.load(fp).get("frameworks", {}))
    except (OSError, json.JSONDecodeError):
        return set()


def verify_board_manifest(path: Path, platform_frameworks: set) -> list:
    """Checks 1, 2, and 4 for one manifest. Returns error strings."""
    errors = []
    rel = path.name
    try:
        with path.open("r", encoding="utf-8") as fp:
            manifest = json.load(fp)
    except OSError as exc:
        return ["%s: cannot read (%s)" % (rel, exc)]
    except json.JSONDecodeError as exc:
        return ["%s: invalid JSON (%s)" % (rel, exc)]

    if not isinstance(manifest, dict):
        return ["%s: manifest must be a JSON object" % rel]

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if not manifest.get(field):
            errors.append("%s: missing required field %r" % (rel, field))

    frameworks = manifest.get("frameworks")
    if not isinstance(frameworks, list) or not frameworks:
        errors.append(
            "%s: 'frameworks' must be a non-empty list" % rel
        )
    else:
        unknown = [fw for fw in frameworks if fw not in platform_frameworks]
        if unknown:
            errors.append(
                "%s: framework(s) %s not declared in platform.json"
                % (rel, ", ".join(sorted(unknown)))
            )

    build = manifest.get("build")
    if isinstance(build, dict) and "zephyr" in build:
        if not isinstance(build["zephyr"], dict):
            errors.append("%s: 'build.zephyr' must be an object" % rel)

    return errors


def verify_boards_dir(
    boards_dir: Path, platform_frameworks: set, expected_ids
) -> list:
    """All checks over one boards directory. Returns error strings."""
    errors = []
    manifests = sorted(boards_dir.glob("*.json")) if boards_dir.is_dir() else []
    if not manifests:
        return ["%s: no *.json manifests found" % boards_dir]

    actual_ids = set()
    for path in manifests:
        actual_ids.add(path.stem)
        errors.extend(verify_board_manifest(path, platform_frameworks))

    expected = set(expected_ids)
    for board_id in sorted(expected - actual_ids):
        errors.append(
            "snapshot: board id %r is listed in SUPPORTED_BOARD_IDS but has "
            "no manifest; update the snapshot if the board was removed" % board_id
        )
    for board_id in sorted(actual_ids - expected):
        errors.append(
            "snapshot: board id %r has a manifest but is missing from "
            "SUPPORTED_BOARD_IDS; add it there deliberately (see the "
            "verify_boards docstring)" % board_id
        )
    return errors


def main() -> int:
    root = repo_root()
    platform_frameworks = load_platform_frameworks(root / "platform.json")
    if not platform_frameworks:
        print(
            "verify_boards: no frameworks found in %s" % (root / "platform.json"),
            file=sys.stderr,
        )
        return 1

    errors = verify_boards_dir(
        root / "boards", platform_frameworks, SUPPORTED_BOARD_IDS
    )
    if errors:
        for error in errors:
            print("verify_boards: %s" % error, file=sys.stderr)
        print(
            "verify_boards: FAILED (%d error(s))" % len(errors), file=sys.stderr
        )
        return 1
    print(
        "verify_boards: OK (%d board manifests)" % len(SUPPORTED_BOARD_IDS)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
