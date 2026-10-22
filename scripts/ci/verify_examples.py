#!/usr/bin/env python3
"""Example-matrix gate: every board/framework pair has a demo.

Adding a board is data + demo envs. This gate turns the second half into a
contract: for every manifest framework of every board there must be at least
one `[env:*]` in examples/ whose `board`/`framework` pair matches. It also
keeps the repository's example URL pinned to this platform's v3 branch, so a
green CI run cannot silently build the predecessor platform from `main`.

Demo layout is demo-grouped (`examples/<demo>/platformio.ini`) because one
file carries all boards of a framework; board-specific hardware samples may
still live under `examples/<board-id>/<sample>/` and are discovered by the
same recursive scan.

    python scripts/ci/verify_examples.py
"""

from __future__ import annotations

import argparse
import configparser
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLATFORM_URL = (
    "https://github.com/Seeed-Studio/platform-seeedboards.git#v3"
)


def _read_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(path, encoding="utf-8")
    return parser


def _value(parser, section: str, key: str) -> str:
    if parser.has_option(section, key):
        return parser.get(section, key).strip()
    if parser.has_section("env") and parser.has_option("env", key):
        return parser.get("env", key).strip()
    return ""


def collect_examples(examples_dir: Path, platform_url: str) -> tuple[set, list]:
    """Return ({(board, framework)}, errors) for every example project."""
    errors = []
    pairs = set()
    projects = sorted(
        path for path in examples_dir.rglob("platformio.ini")
        if ".pio" not in path.parts
    )
    if not projects:
        return pairs, ["no platformio.ini found under %s" % examples_dir]

    for ini_path in projects:
        try:
            parser = _read_ini(ini_path)
        except (OSError, configparser.Error) as exc:
            errors.append("%s: cannot parse (%s)" % (ini_path, exc))
            continue
        env_sections = [s for s in parser.sections() if s.startswith("env:")]
        if not env_sections:
            errors.append("%s: no [env:*] sections" % ini_path)
            continue

        for section in env_sections:
            board = _value(parser, section, "board")
            framework_value = _value(parser, section, "framework")
            platform_value = _value(parser, section, "platform")
            where = "%s [%s]" % (ini_path.relative_to(examples_dir), section)

            if not board:
                errors.append("%s: missing board" % where)
                continue
            if not framework_value:
                errors.append("%s: missing framework" % where)
                continue
            if not platform_value:
                errors.append("%s: missing platform" % where)
            elif platform_value != platform_url:
                errors.append(
                    "%s: platform %r is not the maintained repo URL %r"
                    % (where, platform_value, platform_url))

            for framework in [f.strip() for f in framework_value.split(",") if f.strip()]:
                pairs.add((board, framework))

    return pairs, errors


def check_examples(examples_dir: Path, boards_dir: Path,
                   platform_url: str = DEFAULT_PLATFORM_URL) -> list:
    errors = []
    pairs, parse_errors = collect_examples(examples_dir, platform_url)
    errors.extend(parse_errors)

    expected = set()
    known_boards = set()
    for manifest_path in sorted(boards_dir.glob("*.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append("%s: cannot read manifest (%s)" % (manifest_path, exc))
            continue
        board_id = manifest_path.stem
        known_boards.add(board_id)
        for framework in manifest.get("frameworks") or []:
            expected.add((board_id, framework))

    for board, framework in sorted(pairs):
        if board not in known_boards:
            errors.append("example references unknown board %r" % board)
        elif (board, framework) not in expected:
            errors.append(
                "board %r declares no framework %r but a demo uses it"
                % (board, framework))

    for board, framework in sorted(expected - pairs):
        errors.append(
            "board %r has no demo for framework %r -- add an env to the "
            "matching examples/<demo>/platformio.ini" % (board, framework))

    return errors


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples-dir", type=Path,
                        default=REPO_ROOT / "examples")
    parser.add_argument("--boards-dir", type=Path,
                        default=REPO_ROOT / "boards")
    parser.add_argument("--platform-url", default=DEFAULT_PLATFORM_URL)
    args = parser.parse_args(argv)

    errors = check_examples(args.examples_dir, args.boards_dir,
                            args.platform_url)
    if errors:
        for error in errors:
            print("verify_examples: %s" % error, file=sys.stderr)
        print("verify_examples: FAILED (%d error(s))" % len(errors),
              file=sys.stderr)
        return 1
    print("verify_examples: OK (every board/framework pair has a demo; "
          "example platform URLs pinned to v3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())