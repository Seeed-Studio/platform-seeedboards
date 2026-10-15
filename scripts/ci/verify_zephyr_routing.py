#!/usr/bin/env python3
"""Offline integrity gate for Zephyr routing and fixes layout.

Fast, standalone, no package cache, no network, stdlib-only:

    python scripts/ci/verify_zephyr_routing.py

Checks:
  1. every board declaring the zephyr framework maps to a framework
     package declared in platform.json (build.zephyr.package);
  2. every zephyr board's build.zephyr.board_name has a matching
     directory under zephyr/<family>/boards/seeed/;
  3. build.zephyr.board_name matches the variant-derived Zephyr board.name
     (first component of build.zephyr.variant -- one spelling of the truth);
  4. fixes layout: for every zephyr/<family>/boards/seeed/<board>/fixes/
     directory, every fix file has a fixes.baseline entry and every
     baseline entry has a fix file (two-way correspondence); fix paths
     stay inside the tree; fixes/ directories belong to known boards.

Exit code 0 = all checks pass, 1 = any violation.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASELINE_NAME = "fixes.baseline"
PATCH_SUFFIX = ".patch"
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_platform_packages(platform_json: Path) -> set:
    """Framework package names declared in platform.json (empty on error)."""
    try:
        doc = json.loads(platform_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    packages = doc.get("packages") or {}
    return set(packages) if isinstance(packages, dict) else set()


def load_zephyr_boards(boards_dir: Path) -> dict:
    """Map zephyr-capable board id -> {package, board_name, family, variant}."""
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
        build = manifest.get("build") or {}
        zephyr = build.get("zephyr") or {}
        result[path.stem] = {
            "package": zephyr.get("package"),
            "board_name": zephyr.get("board_name"),
            "family": build.get("family"),
            "variant": zephyr.get("variant"),
        }
    return result


def _iter_fix_files(fixes_dir: Path):
    for path in sorted(fixes_dir.rglob("*")):
        if path.is_file() and path.name != BASELINE_NAME:
            yield path


def verify_fixes_layout(zephyr_root: Path, known_names: set) -> list:
    """Check 4: fixes board-dir layout consistency.

    Fixes live under zephyr/<family>/boards/seeed/<board>/fixes/; the family
    level is discovered by glob (zephyr/*/boards/*/<board>), the same
    convention the builder uses for board dirs.
    """
    errors = []
    for fixes_dir in sorted(zephyr_root.glob("*/boards/*/*/fixes")):
        if not fixes_dir.is_dir():
            continue
        board_dir = fixes_dir.parent
        baseline_path = fixes_dir / BASELINE_NAME
        baseline = {}
        if baseline_path.is_file():
            for line in baseline_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 1)
                if len(parts) != 2:
                    errors.append(
                        "%s: unparseable baseline line %r"
                        % (baseline_path.name, line)
                    )
                    continue
                target, sha = parts[0], parts[1].strip()
                if not _SHA256_RE.fullmatch(sha):
                    # Trailing text (inline comment) or a truncated sha would
                    # pass this gate yet never match a real hexdigest at
                    # build time -- dead runtime gating plus a false
                    # "framework upgraded" warning on every build.
                    errors.append(
                        "%s: invalid sha256 for %r -- expected exactly 64 "
                        "lowercase hex digits with no trailing text (got %r)"
                        % (baseline_path.name, target, sha)
                    )
                    continue
                if target in baseline:
                    errors.append(
                        "%s: duplicate baseline entry for %r"
                        % (baseline_path.name, target)
                    )
                    continue
                baseline[target] = sha
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
                "fixes/ under %s but no board declares this board_name"
                % board_dir
            )
    return errors


def verify_zephyr_routing(
    zephyr_boards: dict,
    platform_packages: set,
    zephyr_root: Path,
) -> list:
    """All checks. zephyr_root is the repo's zephyr/ directory."""
    errors = []

    # Checks 1+2+3: board -> package -> <family>/boards/seeed/<name>/ chain
    # closes, and board_name matches the variant-derived Zephyr board.name.
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

        variant = routing.get("variant") or ""
        derived = variant.split("/")[0].split("@")[0] if variant else ""
        if derived and derived != board_name:
            errors.append(
                "board %r: build.zephyr.board_name %r does not match the "
                "variant-derived board.name %r (variant %r)"
                % (board_id, board_name, derived, variant)
            )

        family = routing.get("family")
        if not family:
            errors.append(
                "board %r declares zephyr but has no build.family" % board_id
            )
            continue
        board_dir = zephyr_root / family / "boards" / "seeed" / board_name
        if not board_dir.is_dir():
            errors.append(
                "board %r: no zephyr/%s/boards/seeed/%s/ directory"
                % (board_id, family, board_name)
            )

    # Check 4: fixes board-dir layout.
    errors.extend(verify_fixes_layout(zephyr_root, known_names))

    return errors


def main() -> int:
    root = repo_root()

    platform_packages = load_platform_packages(root / "platform.json")
    if not platform_packages:
        print("verify_zephyr_routing: platform.json packages unreadable", file=sys.stderr)
        return 1

    zephyr_boards = load_zephyr_boards(root / "boards")
    if not zephyr_boards:
        print("verify_zephyr_routing: no zephyr boards found", file=sys.stderr)
        return 1

    errors = verify_zephyr_routing(
        zephyr_boards, platform_packages, root / "zephyr"
    )
    if errors:
        for error in errors:
            print("verify_zephyr_routing: %s" % error, file=sys.stderr)
        print(
            "verify_zephyr_routing: FAILED (%d error(s))" % len(errors),
            file=sys.stderr,
        )
        return 1
    print("verify_zephyr_routing: OK (%d zephyr boards)" % len(zephyr_boards))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
