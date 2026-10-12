#!/usr/bin/env python3
"""Offline `pio boards` listing smoke test (no registry, no toolchains).

Instantiates this repository's platform class directly through
PlatformFactory and exercises the full get_boards() listing path -- the
exact code path `pio boards` uses, including _add_dynamic_options() for
every board. Regression target: an unmatched board or a None return value
from _add_dynamic_options crashes PlatformIO core's listing
(PlatformPackageManager.get_installed_boards calls get_brief_data() on
every entry).

    python scripts/ci/smoke_pio_boards.py

Exit 0 = all snapshot boards list cleanly, 1 otherwise.
"""

from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main() -> int:
    try:
        from platformio.platform.factory import PlatformFactory
    except ImportError:
        print(
            "smoke_pio_boards: platformio is not importable; skipping "
            "(install with: pip install platformio)",
            file=sys.stderr,
        )
        return 0

    platform = PlatformFactory.new(str(repo_root()))
    boards = platform.get_boards()
    if not isinstance(boards, dict) or not boards:
        print(
            "smoke_pio_boards: get_boards() returned no board mapping",
            file=sys.stderr,
        )
        return 1

    errors = []
    for board_id, board in sorted(boards.items()):
        if board is None:
            errors.append("board %r mapped to None" % board_id)
            continue
        try:
            brief = board.get_brief_data()
        except Exception as exc:  # pylint: disable=broad-except
            errors.append("board %r get_brief_data() failed: %s" % (board_id, exc))
            continue
        if not isinstance(brief, dict) or not brief.get("id"):
            errors.append("board %r produced empty brief data" % board_id)

    # Cross-check against the conscious snapshot in verify_boards.py so the
    # two gates cannot drift apart silently.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify_boards import SUPPORTED_BOARD_IDS  # pylint: disable=import-error

    listed = set(boards)
    expected = set(SUPPORTED_BOARD_IDS)
    for board_id in sorted(expected - listed):
        errors.append("snapshot board %r missing from get_boards() output" % board_id)
    for board_id in sorted(listed - expected):
        errors.append(
            "board %r listed by get_boards() but absent from "
            "verify_boards.SUPPORTED_BOARD_IDS" % board_id
        )

    if errors:
        for error in errors:
            print("smoke_pio_boards: %s" % error, file=sys.stderr)
        print("smoke_pio_boards: FAILED", file=sys.stderr)
        return 1
    print("smoke_pio_boards: OK (%d boards listed)" % len(listed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
