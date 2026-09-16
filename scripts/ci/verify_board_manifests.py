#!/usr/bin/env python3
"""Static validation for board manifests under boards/.

Mirrors the runtime gates that select packages/tools per board, so a
forgotten manifest field fails here at PR time instead of surfacing as a
silent misconfiguration or an obscure build/upload error downstream:

  R1  zephyr in frameworks  -> build.zephyr.{package,variant} required
  R2  arduino in frameworks and build.mcu startswith "nrf52"
        -> build.bsp.name required, value in {adafruit, mbed}
  R3  upload.protocol == "nrfutil-mcumgr"
        -> upload.cdc.{app_vidpid,loader_vidpids} required,
           each VID:PID uppercase hex
  R5  R1 boards -> derived Zephyr board.name (first component of
        build.zephyr.variant, before '/' and '@') is non-empty
  R6  (optional, needs PyYAML) every key under zephyr/fixes.yml `boards:`
        must equal some manifest's derived board.name

Stdlib only; R6 degrades gracefully when PyYAML is absent.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BOARDS_DIR = REPO_ROOT / "boards"
FIXES_YAML = REPO_ROOT / "zephyr" / "fixes.yml"

_VIDPID_RE = re.compile(r"^[0-9A-F]{4}:[0-9A-F]{4}$")
_VALID_BSP = ("adafruit", "mbed")


def _get(obj: Any, dotted: str, default: Any = None) -> Any:
    """BoardConfig-style dotted lookup into a nested dict."""
    cur: Any = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def _derive_board_name(variant: str) -> str:
    """Zephyr board.name: first component of `board[@rev]/soc/...`."""
    return variant.split("/")[0].split("@")[0] if variant else ""


def _check_manifest(path: Path) -> tuple[list[str], str | None]:
    """Return (errors, derived_board_name_or_None) for one manifest."""
    errors: list[str] = []
    derived: str | None = None
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = path.as_posix()

    # R0: parse
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return ([f"ERROR {rel} [json]: {exc}"], None)
    if not isinstance(data, dict):
        return ([f"ERROR {rel} [json]: top-level value is not an object"], None)

    frameworks = data.get("frameworks", [])
    if not isinstance(frameworks, list):
        frameworks = []

    # R1: zephyr
    if "zephyr" in frameworks:
        package = _get(data, "build.zephyr.package", "")
        variant = _get(data, "build.zephyr.variant", "")
        if not package:
            errors.append(
                f"ERROR {rel} [zephyr-package]: 'zephyr' in frameworks requires "
                f"build.zephyr.package (see zephyr/README.md)")
        if not variant:
            errors.append(
                f"ERROR {rel} [zephyr-variant]: 'zephyr' in frameworks requires "
                f"build.zephyr.variant")
        # R5
        derived = _derive_board_name(variant)
        if variant and (not derived or "/" in derived or "@" in derived):
            errors.append(
                f"ERROR {rel} [zephyr-board-name]: derived board.name "
                f"'{derived}' from variant '{variant}' is empty or malformed")

    # R2: arduino on nrf52
    if "arduino" in frameworks:
        mcu = _get(data, "build.mcu", "") or ""
        if isinstance(mcu, str) and mcu.startswith("nrf52"):
            bsp = _get(data, "build.bsp.name", "")
            if not bsp:
                errors.append(
                    f"ERROR {rel} [bsp]: arduino on nrf52 MCU requires "
                    f"build.bsp.name in {{adafruit, mbed}}")
            elif bsp not in _VALID_BSP:
                errors.append(
                    f"ERROR {rel} [bsp]: build.bsp.name '{bsp}' is not in "
                    f"{{adafruit, mbed}}")

    # R3: DFU CDC
    upload = data.get("upload", {})
    if isinstance(upload, dict) and upload.get("protocol") == "nrfutil-mcumgr":
        app = _get(data, "upload.cdc.app_vidpid", "")
        if not app:
            errors.append(
                f"ERROR {rel} [cdc-vidpid]: upload.protocol 'nrfutil-mcumgr' "
                f"requires upload.cdc.app_vidpid")
        elif not _VIDPID_RE.match(app):
            errors.append(
                f"ERROR {rel} [cdc-vidpid]: upload.cdc.app_vidpid '{app}' "
                f"must match {_VIDPID_RE.pattern} (uppercase hex)")
        loaders = _get(data, "upload.cdc.loader_vidpids", [])
        if not isinstance(loaders, list) or not loaders:
            errors.append(
                f"ERROR {rel} [cdc-vidpid]: upload.protocol 'nrfutil-mcumgr' "
                f"requires a non-empty upload.cdc.loader_vidpids list")
        else:
            for i, v in enumerate(loaders):
                if not isinstance(v, str) or not _VIDPID_RE.match(v):
                    errors.append(
                        f"ERROR {rel} [cdc-vidpid]: upload.cdc.loader_vidpids[{i}] "
                        f"'{v}' must match {_VIDPID_RE.pattern} (uppercase hex)")

    return (errors, derived)


def _check_fixes_keys(derived_names: set[str]) -> list[str]:
    """R6: every fixes.yml board key must reference a known board name."""
    errors: list[str] = []
    if not FIXES_YAML.exists():
        return errors  # no fixes file -> nothing to cross-check
    try:
        import yaml  # type: ignore
    except ImportError:
        print(f"note: {FIXES_YAML.relative_to(REPO_ROOT)} exists but PyYAML is "
              f"not installed; R6 cross-check skipped.", file=sys.stderr)
        return errors
    with FIXES_YAML.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    boards = doc.get("boards", {}) if isinstance(doc, dict) else {}
    if not isinstance(boards, dict):
        return [f"ERROR zephyr/fixes.yml: top-level 'boards' is not a mapping"]
    for key in boards:
        if key not in derived_names:
            errors.append(
                f"ERROR zephyr/fixes.yml [orphan]: boards key '{key}' matches no "
                f"board manifest's derived name ({sorted(derived_names) or 'none'})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--boards-dir", type=Path, default=DEFAULT_BOARDS_DIR,
                        help="directory of board manifests (default: boards/)")
    args = parser.parse_args()

    boards_dir: Path = args.boards_dir
    if not boards_dir.is_dir():
        print(f"error: boards dir not found: {boards_dir}", file=sys.stderr)
        return 2

    all_errors: list[str] = []
    derived_names: set[str] = set()
    checked = 0
    for path in sorted(boards_dir.glob("*.json")):
        checked += 1
        errs, derived = _check_manifest(path)
        all_errors.extend(errs)
        if derived:
            derived_names.add(derived)

    all_errors.extend(_check_fixes_keys(derived_names))

    if all_errors:
        for line in all_errors:
            print(line)
    print(f"checked {checked} manifest(s), {len(all_errors)} error(s)")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main())
