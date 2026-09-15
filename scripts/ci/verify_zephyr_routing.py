#!/usr/bin/env python3
"""Offline integrity gate for Zephyr routing and fixes layout.

Fast, standalone, no package cache, no network (invariant-gate pattern
from .agents/notes/proposed/2026-08-17-ai-workflow-adaptation.md):

    python scripts/ci/verify_zephyr_routing.py

Checks:
  1. every board declaring the zephyr framework maps to a framework
     package declared in platform.json (build.zephyr.package);
  2. every zephyr board's build.zephyr.board_name has a matching
     directory under zephyr/boards/arm/;
  3. fixes v2 layout: for every zephyr/boards/arm/<board>/fixes/
     directory, every fix file has a fixes.baseline entry and every
     baseline entry has a fix file (two-way correspondence); fix paths
     stay inside the tree;
  4. legacy layout (pending removal): every boards: key in
     zephyr/fixes.yml and every zephyr/patches//overrides/ directory
     corresponds to a known zephyr board; fix targets are sane.

Exit code 0 = all checks pass, 1 = any violation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASELINE_NAME = "fixes.baseline"
PATCH_SUFFIX = ".patch"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_zephyr_boards(boards_dir: Path) -> dict:
    """Map zephyr-capable board id -> {package, board_name} from manifests."""
    result = {}
    if not boards_dir.is_dir():
        return result
    for path in sorted(boards_dir.glob("*.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # verify_boards.py reports manifest corruption
        if "zephyr" not in (manifest.get("frameworks") or []):
            continue
        zephyr = manifest.get("build", {}).get("zephyr") or {}
        result[path.stem] = {
            "package": zephyr.get("package"),
            "board_name": zephyr.get("board_name"),
        }
    return result


def _iter_fix_files(fixes_dir: Path):
    for path in sorted(fixes_dir.rglob("*")):
        if path.is_file() and path.name != BASELINE_NAME:
            yield path


def verify_fixes_layout(boards_arm_root: Path, known_names: set) -> list:
    """Check 3: fixes v2 board-dir layout consistency."""
    errors = []
    for board_dir in sorted(boards_arm_root.iterdir()) if boards_arm_root.is_dir() else []:
        fixes_dir = board_dir / "fixes"
        if not fixes_dir.is_dir():
            continue
        baseline_path = fixes_dir / BASELINE_NAME
        baseline = {}
        if baseline_path.is_file():
            for line in baseline_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    baseline[parts[0]] = parts[1].strip()
                else:
                    errors.append(
                        "%s: unparseable baseline line %r"
                        % (baseline_path.name, line)
                    )
        else:
            errors.append(
                "fixes/ for board %r has no %s" % (board_dir.name, BASELINE_NAME)
            )

        fix_targets = set()
        for fix_file in _iter_fix_files(fixes_dir):
            rel = fix_file.relative_to(fixes_dir).as_posix()
            if rel.startswith("/") or ".." in fix_file.parts:
                errors.append("fix escapes the fixes tree: %s" % fix_file)
                continue
            target = rel[: -len(PATCH_SUFFIX)] if rel.endswith(PATCH_SUFFIX) else rel
            fix_targets.add(target)
            if target not in baseline:
                errors.append(
                    "fix %s (board %r) has no %s entry"
                    % (rel, board_dir.name, BASELINE_NAME)
                )
        for target in sorted(set(baseline) - fix_targets):
            errors.append(
                "%s lists target %r (board %r) with no fix file"
                % (BASELINE_NAME, target, board_dir.name)
            )

        if board_dir.name not in known_names:
            errors.append(
                "fixes/ under zephyr/boards/arm/%s/ but no board declares "
                "this board_name" % board_dir.name
            )
    return errors


def verify_zephyr_routing(
    zephyr_boards: dict,
    platform_packages: set,
    zephyr_root: Path,
    fixes: dict,
) -> list:
    """All checks. zephyr_root is the repo's zephyr/ directory; fixes is the
    parsed legacy zephyr/fixes.yml content ({} when absent)."""
    errors = []

    # Checks 1+2: board -> package -> boards/arm/<name>/ chain closes.
    known_names = set()
    for board_id, routing in sorted(zephyr_boards.items()):
        package = routing.get("package")
        if not package:
            errors.append(
                "board %r declares zephyr but has no build.zephyr.package"
                % board_id
            )
        elif package not in platform_packages:
            errors.append(
                "board %r: package %r is not declared in platform.json"
                % (board_id, package)
            )

        board_name = routing.get("board_name")
        if not board_name:
            errors.append(
                "board %r declares zephyr but has no build.zephyr.board_name"
                % board_id
            )
            continue
        known_names.add(board_name)
        if not (zephyr_root / "boards" / "arm" / board_name).is_dir():
            errors.append(
                "board %r: no zephyr/boards/arm/%s/ directory" % (board_id, board_name)
            )

    # Check 3: fixes v2 board-dir layout.
    errors.extend(
        verify_fixes_layout(zephyr_root / "boards" / "arm", known_names)
    )

    # Check 4: legacy registry layout (until it is removed).
    fixes_boards = set((fixes.get("boards") or {}).keys())
    for name in sorted(fixes_boards - known_names):
        errors.append(
            "fixes.yml: board %r has fixes but is not a known zephyr "
            "board_name (boards/arm/ or build.zephyr.board_name mismatch)" % name
        )
    for subdir in ("patches", "overrides"):
        root = zephyr_root / subdir
        if not root.is_dir():
            continue
        for entry in sorted(p.name for p in root.iterdir() if p.is_dir()):
            if entry not in known_names:
                errors.append(
                    "zephyr/%s/%s/ exists for board %r but no board declares "
                    "it (orphan fix sources)" % (subdir, entry, entry)
                )
    for name, section in sorted((fixes.get("boards") or {}).items()):
        for fix in section.get("fixes") or []:
            target = fix.get("target")
            if not target or target.startswith("/") or ".." in Path(target).parts:
                errors.append(
                    "fixes.yml: fix %r has invalid target %r" % (fix.get("id"), target)
                )

    return errors


def main() -> int:
    root = repo_root()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify_boards import load_platform_packages

    platform_packages = load_platform_packages(root / "platform.json")
    if not platform_packages:
        print("verify_zephyr_routing: platform.json packages unreadable", file=sys.stderr)
        return 1

    zephyr_boards = load_zephyr_boards(root / "boards")
    if not zephyr_boards:
        print("verify_zephyr_routing: no zephyr boards found", file=sys.stderr)
        return 1

    fixes = {}
    fixes_path = root / "zephyr" / "fixes.yml"
    if fixes_path.is_file():
        try:
            import yaml

            fixes = yaml.safe_load(fixes_path.read_text(encoding="utf-8")) or {}
        except ImportError:
            print(
                "verify_zephyr_routing: pyyaml is required (pip install pyyaml)",
                file=sys.stderr,
            )
            return 1

    errors = verify_zephyr_routing(
        zephyr_boards, platform_packages, root / "zephyr", fixes
    )
    if errors:
        for error in errors:
            print("verify_zephyr_routing: %s" % error, file=sys.stderr)
        print(
            "verify_zephyr_routing: FAILED (%d error(s))" % len(errors),
            file=sys.stderr,
        )
        return 1
    print(
        "verify_zephyr_routing: OK (%d zephyr boards, %d fixes.yml boards)"
        % (len(zephyr_boards), len((fixes.get("boards") or {})))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
