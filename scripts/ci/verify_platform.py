#!/usr/bin/env python3
"""Runtime contract gate for the family/package/manifest boundary.

Static JSON checks (verify_boards.py) cannot see the Python side: a family
can require a package that platform.json never declares, a board can route
to a family whose debug injection asserts, or a build script path can rot.
This gate loads the real platform through PlatformIO, then for every board
and declared framework:

  * resolves build.chip_family through the live ChipFamily registry;
  * calls family.required_packages() and checks every returned name is
    declared in platform.json;
  * calls family.upload_protocol() and checks it is non-empty;
  * calls family.inject_debug_tools() on a fresh copy of the manifest and
    checks it produces debug.tools without raising;
  * checks family.build_script() and the framework entry script
    (arduino_script/zephyr_script) resolve to existing files.

It also enforces the ADR-0002 default: every package declaration is
optional; families opt packages in per board. Non-optional packages are
the exact way cross-family bloat creeps back in.

    python scripts/ci/verify_platform.py
"""

from __future__ import annotations

import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_VIDPID_RE = re.compile(r"^[0-9A-F]{4}:[0-9A-F]{4}$")
# Allowed build.<framework>.package values are checked against platform.json;
# this map only says which manifest key selects the package per framework.
_FRAMEWORK_PACKAGE_KEYS = {
    "arduino": "build.arduino.package",
    "espidf": "build.espidf.package",
    "zephyr": "build.zephyr.package",
}


class FakeBoard:
    """Minimal PlatformIO BoardConfig stand-in (dotted get + manifest)."""

    def __init__(self, board_id: str, manifest: dict):
        self.id = board_id
        self.manifest = copy.deepcopy(manifest)
        self.manifest_path = str(REPO_ROOT / "boards" / (board_id + ".json"))

    def get(self, key, default=None):
        cur = self.manifest
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur


class FakeEnv:
    def subst(self, value):
        return value


def _get(obj, dotted, default=None):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _load_platform():
    # Keep PlatformIO state out of the user's home during the gate.
    core_dir = os.environ.get("PLATFORMIO_CORE_DIR")
    if not core_dir:
        core_dir = tempfile.mkdtemp(prefix="pio-verify-")
        os.environ["PLATFORMIO_CORE_DIR"] = core_dir

    # Import PlatformIO before putting the repository root on sys.path:
    # the repo's platform.py would otherwise shadow the stdlib `platform`
    # module that PlatformIO (and uuid) import during startup.
    import platform as _stdlib_platform  # noqa: F401
    from platformio.platform.factory import PlatformFactory

    sys.path.insert(0, str(REPO_ROOT))
    return PlatformFactory.new(str(REPO_ROOT))


def _resolve_script(relative: str) -> Path:
    path = Path(relative)
    if not path.is_absolute():
        path = REPO_ROOT / "builder" / "frameworks" / path
    return path.resolve()


def verify_repo() -> list:
    errors = []
    try:
        platform_obj = _load_platform()
    except Exception as exc:  # pylint: disable=broad-except
        return ["platform load failed: %s: %s" % (type(exc).__name__, exc)]

    try:
        from families.base import ChipFamily
        import families  # noqa: F401  (registration side effect)
    except Exception as exc:  # pylint: disable=broad-except
        return ["families import failed: %s: %s" % (type(exc).__name__, exc)]

    packages = platform_obj.packages
    frameworks = platform_obj.frameworks or {}

    # ADR-0002 default: all package declarations are optional.
    for name, options in sorted(packages.items()):
        if options.get("optional") is not True:
            errors.append(
                "platform.json: package %r is not optional:true -- families "
                "must activate packages per board (ADR-0002)" % name)

    boards_dir = REPO_ROOT / "boards"
    board_ids = sorted(path.stem for path in boards_dir.glob("*.json"))
    try:
        live_boards = platform_obj.get_boards()
    except Exception as exc:  # pylint: disable=broad-except
        return errors + ["platform.get_boards() failed: %s: %s"
                         % (type(exc).__name__, exc)]

    missing = sorted(set(board_ids) - set(live_boards))
    extra = sorted(set(live_boards) - set(board_ids))
    if missing:
        errors.append("boards not returned by get_boards(): %s" % ", ".join(missing))
    if extra:
        errors.append("get_boards() returned undeclared boards: %s" % ", ".join(extra))

    for board_id in board_ids:
        manifest_path = boards_dir / (board_id + ".json")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append("%s: cannot read manifest (%s)" % (board_id, exc))
            continue

        family_id = _get(manifest, "build.chip_family")
        try:
            family = ChipFamily.get(family_id)
        except KeyError as exc:
            errors.append("%s: %s" % (board_id, exc))
            continue
        if family is None:
            errors.append("%s: no chip_family" % board_id)
            continue

        board_frameworks = manifest.get("frameworks") or []
        for framework in board_frameworks:
            if framework not in frameworks:
                errors.append(
                    "%s: framework %r not declared in platform.json"
                    % (board_id, framework))
                continue

            variables = {
                "pioframework": [framework],
                "upload_protocol": _get(manifest, "upload.protocol", ""),
                "board_build.mcu": _get(manifest, "board_build.mcu", ""),
            }
            try:
                required = family.required_packages(manifest, variables=variables)
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(
                    "%s/%s: required_packages() raised %s: %s"
                    % (board_id, framework, type(exc).__name__, exc))
                continue
            if not isinstance(required, dict):
                errors.append(
                    "%s/%s: required_packages() must return a dict"
                    % (board_id, framework))
                continue
            for name in sorted(required):
                if name not in packages:
                    errors.append(
                        "%s/%s: family requires undeclared package %r"
                        % (board_id, framework, name))

            package_key = _FRAMEWORK_PACKAGE_KEYS.get(framework)
            per_board_package = _get(manifest, package_key) if package_key else None
            if per_board_package and per_board_package not in packages:
                errors.append(
                    "%s/%s: %s %r is not declared in platform.json"
                    % (board_id, framework, package_key, per_board_package))

            try:
                script = family.arduino_script(FakeEnv(), FakeBoard(
                    board_id, manifest)) if framework == "arduino" else (
                    family.zephyr_script(FakeEnv(), FakeBoard(board_id, manifest))
                    if framework == "zephyr" else None)
            except NotImplementedError:
                errors.append(
                    "%s/%s: family has no %s entry script"
                    % (board_id, framework, framework))
                continue
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(
                    "%s/%s: framework script lookup raised %s: %s"
                    % (board_id, framework, type(exc).__name__, exc))
                continue
            if script and not _resolve_script(script).is_file():
                errors.append(
                    "%s/%s: framework script %r does not exist"
                    % (board_id, framework, script))

        try:
            upload = family.upload_protocol(FakeBoard(board_id, manifest))
        except Exception as exc:  # pylint: disable=broad-except
            errors.append(
                "%s: upload_protocol() raised %s: %s"
                % (board_id, type(exc).__name__, exc))
        else:
            if not upload:
                errors.append("%s: upload_protocol() returned empty" % board_id)

        try:
            build_script = family.build_script(FakeEnv(), FakeBoard(
                board_id, manifest))
        except Exception as exc:  # pylint: disable=broad-except
            errors.append(
                "%s: build_script() raised %s: %s"
                % (board_id, type(exc).__name__, exc))
        else:
            if not Path(build_script).is_file():
                errors.append(
                    "%s: build script %r does not exist"
                    % (board_id, build_script))

        fake = FakeBoard(board_id, manifest)
        try:
            family.inject_debug_tools(fake)
        except Exception as exc:  # pylint: disable=broad-except
            errors.append(
                "%s: inject_debug_tools() raised %s: %s"
                % (board_id, type(exc).__name__, exc))
        else:
            tools = _get(fake.manifest, "debug.tools", {})
            if not tools:
                errors.append("%s: inject_debug_tools() produced no tools" % board_id)

        # The CDC block is consumed by the nrfutil-mcumgr upload path.
        if _get(manifest, "upload.protocol") == "nrfutil-mcumgr":
            app = _get(manifest, "upload.cdc.app_vidpid", "")
            loaders = _get(manifest, "upload.cdc.loader_vidpids", [])
            if not app or not _VIDPID_RE.match(app):
                errors.append(
                    "%s: nrfutil-mcumgr needs upload.cdc.app_vidpid as "
                    "UPPER:UPPER hex" % board_id)
            if not isinstance(loaders, list) or not loaders:
                errors.append(
                    "%s: nrfutil-mcumgr needs upload.cdc.loader_vidpids"
                    % board_id)
            else:
                for value in loaders:
                    if not isinstance(value, str) or not _VIDPID_RE.match(value):
                        errors.append(
                            "%s: bad upload.cdc.loader_vidpids entry %r"
                            % (board_id, value))

    return errors


def main() -> int:
    errors = verify_repo()
    if errors:
        for error in errors:
            print("verify_platform: %s" % error, file=sys.stderr)
        print("verify_platform: FAILED (%d error(s))" % len(errors),
              file=sys.stderr)
        return 1
    print("verify_platform: OK (boards load; family packages, scripts and "
          "debug tools resolve; all packages optional)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())