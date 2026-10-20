#!/usr/bin/env python3
"""Offline gate: board manifests.

Fast, standalone, package-cache-free. Run from anywhere:

    python scripts/ci/verify_boards.py

Checks (bootstrap-aware -- an empty boards/ with an empty snapshot
passes with a notice):
  1. every boards/*.json parses and carries name/url/vendor + the
     build.chip_family routing key;
  2. build.chip_family is a known ChipFamily id (from the live
     registry -- families/ must be importable);
  3. a concrete ChipFamily subclass must declare non-empty family_ids
     (the post-creation guard base.py cannot do in __init_subclass__).

Exit 0 = pass, 1 = violations listed per file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REQUIRED_FIELDS = ("name", "url", "vendor")
ROUTING_KEY = "build.chip_family"

# Conscious snapshot of supported board ids; adding/removing a board is
# a deliberate edit here (the failure message says so).
SUPPORTED_BOARD_IDS = (
    "seeed-xiao-esp32-c3",
    "seeed-xiao-esp32-c5",
    "seeed-xiao-esp32-c6",
    "seeed-xiao-esp32-s3-plus",
    "seeed-xiao-esp32-s3-sense",
    "seeed-xiao-samd",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_registry():
    sys.path.insert(0, str(repo_root()))
    from families.base import ChipFamily

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    return ChipFamily


def _iter_chipfamily_classes(chip_family_cls):
    seen = set()
    # Enumerate subclasses transitively for the concreteness check.
    stack = list(chip_family_cls.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if cls in seen:
            continue
        seen.add(cls)
        yield cls


def verify_families_concreteness(chip_family_cls) -> list:
    """Guard: a concrete subclass (no abstract methods left) must carry
    non-empty family_ids, else it silently registers nothing."""
    errors = []
    for cls in _iter_chipfamily_classes(chip_family_cls):
        if getattr(cls, "__abstractmethods__", None):
            continue  # intermediate base; skip by design
        if not getattr(cls, "family_ids", ()):
            errors.append(
                "families: concrete ChipFamily %s declares empty family_ids "
                "-- it registers nothing (declare ids or make it abstract)"
                % cls.__name__
            )
    return errors


def verify_board_manifest(path: Path, known_family_ids: set) -> list:
    errors = []
    rel = path.name
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return ["%s: cannot read (%s)" % (rel, exc)]
    except json.JSONDecodeError as exc:
        return ["%s: invalid JSON (%s)" % (rel, exc)]

    if not isinstance(manifest, dict):
        return ["%s: manifest must be a JSON object" % rel]

    for field in REQUIRED_FIELDS:
        if not manifest.get(field):
            errors.append("%s: missing required field %r" % (rel, field))

    family = (manifest.get("build") or {}).get("chip_family")
    if not family:
        errors.append(
            "%s: missing %r -- the routing key that selects the family"
            % (rel, ROUTING_KEY)
        )
    elif known_family_ids and family not in known_family_ids:
        errors.append(
            "%s: %s %r is not a registered family (known: %s)"
            % (rel, ROUTING_KEY, family, ", ".join(sorted(known_family_ids)))
        )
    return errors


def verify_boards_dir(boards_dir: Path, known_family_ids: set, expected_ids) -> list:
    errors = []
    manifests = sorted(boards_dir.glob("*.json")) if boards_dir.is_dir() else []
    if not manifests and not expected_ids:
        return []  # bootstrap: no boards declared yet
    if not manifests:
        return [
            "snapshot lists %d board(s) but %s has no manifests"
            % (len(expected_ids), boards_dir)
        ]

    actual_ids = set()
    for path in manifests:
        actual_ids.add(path.stem)
        errors.extend(verify_board_manifest(path, known_family_ids))

    expected = set(expected_ids)
    for board_id in sorted(expected - actual_ids):
        errors.append(
            "snapshot: board id %r listed but no manifest; update the "
            "snapshot if the board was removed" % board_id
        )
    for board_id in sorted(actual_ids - expected):
        errors.append(
            "snapshot: board id %r has a manifest but is missing from "
            "SUPPORTED_BOARD_IDS; add it deliberately" % board_id
        )
    return errors


def main() -> int:
    root = repo_root()
    errors = []

    try:
        chip_family_cls = _load_registry()
    except Exception as exc:  # pylint: disable=broad-except
        print("verify_boards: cannot import families.base: %s" % exc, file=sys.stderr)
        return 1

    known = chip_family_cls.known_family_ids()
    errors.extend(verify_families_concreteness(chip_family_cls))
    errors.extend(verify_boards_dir(root / "boards", known, SUPPORTED_BOARD_IDS))

    if errors:
        for error in errors:
            print("verify_boards: %s" % error, file=sys.stderr)
        print(
            "verify_boards: FAILED (%d error(s))" % len(errors), file=sys.stderr
        )
        return 1
    if not SUPPORTED_BOARD_IDS:
        print("verify_boards: bootstrap state OK (no boards declared yet)")
    else:
        print("verify_boards: OK (%d boards, families: %s)"
              % (len(SUPPORTED_BOARD_IDS), ", ".join(known) or "(none)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
