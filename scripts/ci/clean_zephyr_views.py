#!/usr/bin/env python3
"""List or prune ADR-0006 Zephyr framework views.

Views live under $PLATFORMIO_CORE_DIR/zephyr-views. They are cache, not
source: keep a few recent ones for fast rebuilds and remove the rest.

    python scripts/ci/clean_zephyr_views.py --dry-run
    python scripts/ci/clean_zephyr_views.py --keep 3
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path

VIEW_MARKER = ".pio-view-key"


def default_root() -> Path:
    core = os.environ.get("PLATFORMIO_CORE_DIR") or os.path.expanduser(
        "~/.platformio")
    return Path(core) / "zephyr-views"


def collect_views(root: Path) -> list:
    if not root.is_dir():
        return []
    return [
        path for path in root.iterdir()
        if path.is_dir() and (path / VIEW_MARKER).is_file()
    ]


def apparent_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def prune_views(root: Path, keep: int = 3, dry_run: bool = False):
    """Return (kept, removed) lists, deleting removals unless dry_run."""
    views = sorted(
        collect_views(root),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    keep = max(0, int(keep))
    kept, removed = views[:keep], views[keep:]
    if not dry_run:
        for path in removed:
            shutil.rmtree(path, ignore_errors=True)
    return kept, removed


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument("--keep", type=int, default=3,
                        help="number of newest views to keep (default: 3)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    root = args.root
    views = sorted(
        collect_views(root),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not views:
        print("clean_zephyr_views: no views under %s" % root)
        return 0

    for path in views:
        age = max(0, time.time() - path.stat().st_mtime)
        print("  %-70s %8.1f MB  %.1f h old" % (
            path.name, apparent_size(path) / (1024 * 1024), age / 3600))
    kept, removed = prune_views(root, args.keep, args.dry_run)
    if args.dry_run:
        print("clean_zephyr_views: dry-run; would keep %d, remove %d"
              % (len(kept), len(removed)))
    else:
        print("clean_zephyr_views: kept %d, removed %d"
              % (len(kept), len(removed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())