# SPDX-License-Identifier: Apache-2.0
"""
Zephyr framework fixes dispatcher (调度器).

Reads zephyr/fixes.yml and applies every matching fix to the framework-zephyr
package, dispatching each to the right executor (zephyr_patch.apply_patch for
patches, zephyr_override.apply_override for overrides). Two-level gating keeps
fixes from leaking across boards or framework versions:

  1) board/package gating — only the boards[<board.name>] section is taken;
     a board absent from fixes.yml simply has no fixes applied.
  2) version gating       — only fixes whose applies_to matches the current
     Zephyr version (resolved by _get_framework_version()) are applied.

This is the only module that reads the manifest; the executors are pure.

Interface:
    apply_all(platform_dir, framework_dir, zephyr_board, version)
"""

import os
import sys
from os.path import dirname, join

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.run(["pip", "install", "pyyaml"], check=True)
    import yaml

# Executors live next to this module.
_HERE = dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import zephyr_patch
import zephyr_override


FIXES_YML = "fixes.yml"
PATCHES_SUBDIR = "patches"
OVERRIDES_SUBDIR = "overrides"


def apply_all(platform_dir, framework_dir, zephyr_board, version):
    """Apply all fixes from zephyr/fixes.yml matching (zephyr_board, version).

    zephyr_board: board.name (e.g. "xiao_stm32c5"). Absent from fixes.yml => no-op.
    version: Zephyr version string (e.g. "4.4.0", from _get_framework_version()).
    """
    fixes_yml = join(platform_dir, "zephyr", FIXES_YML)
    if not os.path.isfile(fixes_yml):
        return  # no manifest → no fixes

    with open(fixes_yml, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    board_section = (data.get("boards") or {}).get(zephyr_board)
    if not board_section:
        return  # this board has no local fixes

    fixes = board_section.get("fixes") or []
    if not fixes:
        return

    print("Applying %d Zephyr fix(es) for board '%s' (Zephyr %s)..."
          % (len(fixes), zephyr_board, version))

    for fix in fixes:
        _apply_one_fix(platform_dir, framework_dir, zephyr_board, fix, version)


def _apply_one_fix(platform_dir, framework_dir, zephyr_board, fix, version):
    fix_id = fix.get("id", "<no-id>")
    fix_type = fix.get("type")
    applies_to = fix.get("applies_to") or []

    if not _version_matches(version, applies_to):
        print("  skip [%s]: version %s not in %s" % (fix_id, version, applies_to))
        return

    if fix_type == "patch":
        src = join(platform_dir, "zephyr", PATCHES_SUBDIR, zephyr_board, fix.get("path", ""))
        if not os.path.isfile(src):
            raise RuntimeError("patch source not found for fix '%s': %s" % (fix_id, src))
        zephyr_patch.apply_patch(src, framework_dir, fix.get("target"))

    elif fix_type == "override":
        src = join(platform_dir, "zephyr", OVERRIDES_SUBDIR, zephyr_board, fix.get("path", ""))
        if not os.path.isfile(src):
            raise RuntimeError("override source not found for fix '%s': %s" % (fix_id, src))
        zephyr_override.apply_override(
            src, framework_dir, fix.get("target"), fix.get("baseline_sha")
        )

    else:
        raise RuntimeError("unknown fix type %r for fix '%s'" % (fix_type, fix_id))


def _version_matches(version, applies_to):
    """applies_to: list of version specs. A plain value like "4.4.0" is an exact
    match (string compare, no dependency on packaging). A spec starting with a
    comparison operator (>=, <, ==, !=) is a PEP 440 range parsed via packaging
    if available. Any spec matching → True; empty list → False."""
    if not applies_to:
        return False

    for spec in applies_to:
        spec = str(spec).strip()
        if not spec:
            continue

        if spec[0] in "<>=!":
            # range spec — needs packaging
            try:
                from packaging.specifiers import SpecifierSet
                from packaging.version import Version
                if Version(str(version)) in SpecifierSet(spec):
                    return True
            except Exception:
                continue
            continue

        # exact version — string compare first (no dependency), then Version
        if str(version) == spec:
            return True
        try:
            from packaging.version import Version
            if Version(str(version)) == Version(spec):
                return True
        except Exception:
            pass

    return False
