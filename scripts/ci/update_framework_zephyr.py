#!/usr/bin/env python3
"""Update PlatformIO framework-zephyr version in platform.json.

Data source (stable JSON API):
  https://api.registry.platformio.org/v3/packages/platformio/tool/framework-zephyr

Why text edit (not JSON re-serialize):
  platform.json in this repo is hand-formatted and contains inconsistent spacing;
  re-serializing would create a huge noisy diff.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


REGISTRY_API_URL = "https://api.registry.platformio.org/v3/packages/platformio/tool/framework-zephyr"
DEFAULT_PLATFORM_JSON = Path(__file__).resolve().parents[2] / "platform.json"


@dataclass(frozen=True)
class UpdateResult:
    changed: bool
    old_version: str
    new_version: str


def _fetch_latest_version_name() -> str:
    with urllib.request.urlopen(REGISTRY_API_URL, timeout=30) as resp:
        payload = resp.read().decode("utf-8")
    data = json.loads(payload)

    # Prefer top-level "version" which represents the latest.
    latest = data.get("version")
    if isinstance(latest, dict) and isinstance(latest.get("name"), str):
        return latest["name"].strip()

    # Fallback: scan versions list.
    versions = data.get("versions")
    if isinstance(versions, list):
        for item in versions:
            if isinstance(item, dict) and item.get("is_latest") is True and isinstance(item.get("name"), str):
                return item["name"].strip()
        if versions and isinstance(versions[0], dict) and isinstance(versions[0].get("name"), str):
            return versions[0]["name"].strip()

    raise RuntimeError("Unable to determine latest framework-zephyr version from registry API")


def _find_object_span(text: str, start_key_pos: int) -> Tuple[int, int]:
    """Return (obj_start_index, obj_end_index_exclusive) for the JSON object after a key.

    This is a small JSON-aware brace matcher that understands strings/escapes.
    """

    # Find the first '{' after the key.
    obj_start = text.find("{", start_key_pos)
    if obj_start == -1:
        raise ValueError("Could not find object start '{' after key")

    in_string = False
    escape = False
    depth = 0

    for i in range(obj_start, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return obj_start, i + 1

    raise ValueError("Unterminated object while matching braces")


def _update_platform_json_text(text: str, latest_version: str) -> Tuple[UpdateResult, str]:
    packages_pos = text.find('"packages"')
    if packages_pos == -1:
        raise ValueError('Could not find top-level "packages" in platform.json')

    # Find the package entry key inside the packages section.
    key_match = re.search(r'"framework-zephyr"\s*:\s*\{', text[packages_pos:])
    if not key_match:
        raise ValueError('Could not find "framework-zephyr" package entry in platform.json')

    key_pos = packages_pos + key_match.start()
    obj_start, obj_end = _find_object_span(text, key_pos)
    obj_text = text[obj_start:obj_end]

    ver_match = re.search(r'(\n\s*"version"\s*:\s*")([^"]+)("\s*,?)', obj_text)
    if not ver_match:
        raise ValueError('Could not find "version" field within packages.framework-zephyr object')

    old_version = ver_match.group(2)
    prefix = "~" if old_version.strip().startswith("~") else ""
    new_version = f"{prefix}{latest_version}"

    if old_version.strip() == new_version:
        return UpdateResult(changed=False, old_version=old_version, new_version=new_version), text

    new_obj_text = obj_text[: ver_match.start(2)] + new_version + obj_text[ver_match.end(2) :]
    new_text = text[:obj_start] + new_obj_text + text[obj_end:]

    return UpdateResult(changed=True, old_version=old_version, new_version=new_version), new_text


def _write_github_output(**kv: str) -> None:
    out_path = os.environ.get("GITHUB_OUTPUT")
    if not out_path:
        return
    with open(out_path, "a", encoding="utf-8") as f:
        for k, v in kv.items():
            f.write(f"{k}={v}\n")


def main(argv: list[str]) -> int:
    platform_json_path = Path(os.environ.get("PLATFORM_JSON", str(DEFAULT_PLATFORM_JSON)))

    if not platform_json_path.exists():
        print(f"ERROR: platform.json not found at {platform_json_path}", file=sys.stderr)
        return 2

    latest = _fetch_latest_version_name()

    original_text = platform_json_path.read_text(encoding="utf-8")

    update, new_text = _update_platform_json_text(original_text, latest)

    print(f"framework-zephyr: {update.old_version} -> {update.new_version}")

    if update.changed:
        platform_json_path.write_text(new_text, encoding="utf-8")

    _write_github_output(
        changed=str(update.changed).lower(),
        old_version=update.old_version.strip(),
        new_version=update.new_version.strip(),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
