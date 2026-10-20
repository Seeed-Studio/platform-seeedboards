#!/usr/bin/env python3
"""Offline gate: zero-string routing in the core files (ADR-0001).

Scans platform.py and builder/main.py for chip-family literals; the
core must route exclusively through the ChipFamily registry. Also
verifies platform.json parses and its frameworks map to existing
scripts.

    python scripts/ci/verify_core.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Chip-family tokens the core must never carry (sourced from upstream
# platform naming conventions; extend when a family onboard requires).
FORBIDDEN = (
    r"\besp32", r"\bsamd", r"\bnrf5", r"\brp2040", r"\brp2350",
    r"\bstm32", r"\bra4m1", r"\bmg24", r"\bsilabs", r"\brenesas",
)

CORE_FILES = ("platform.py", "builder/main.py")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def verify_zero_string() -> list:
    errors = []
    for rel in CORE_FILES:
        path = repo_root() / rel
        if not path.is_file():
            errors.append("core: %s not found" % rel)
            continue
        for i, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.split("#", 1)[0]  # comments exempt
            for pattern in FORBIDDEN:
                if re.search(pattern, stripped, re.IGNORECASE):
                    errors.append(
                        "%s:%d: chip-family literal %r in core routing "
                        "-- use the ChipFamily registry (ADR-0001): %s"
                        % (rel, i, pattern, line.strip()[:70])
                    )
    return errors


def verify_platform_json() -> list:
    errors = []
    path = repo_root() / "platform.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return ["platform.json: %s" % exc]

    for name, fw in (manifest.get("frameworks") or {}).items():
        script = fw.get("script")
        if not script:
            continue
        if not (repo_root() / script).is_file():
            errors.append(
                "platform.json: frameworks.%s script %r not found" % (name, script)
            )
    return errors


def main() -> int:
    errors = verify_zero_string() + verify_platform_json()
    if errors:
        for error in errors:
            print("verify_core: %s" % error, file=sys.stderr)
        return 1
    print("verify_core: OK (zero-string routing clean; platform.json valid)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
