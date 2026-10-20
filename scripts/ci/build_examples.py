#!/usr/bin/env python3
"""Build every example project under examples/ for one framework.

CI wrapper for the T1/T2 validation tiers (ADR-0004): discovers
projects by their declared `framework =` line, rewrites the platform
URLs to the local checkout, and builds every environment. The ADR-0005
merge gate consumes the exit code.

    python scripts/ci/build_examples.py --framework arduino
    python scripts/ci/build_examples.py --framework zephyr
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


REPO_PLATFORM_PREFIXES = (
    "https://github.com/Seeed-Studio/platform-seeedboards",
)


def find_projects(examples_dir: Path) -> list:
    return sorted(set(p.parent for p in examples_dir.rglob("platformio.ini")))


def uses_framework(ini_text: str, framework: str) -> bool:
    for line in ini_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped.lower().startswith("framework"):
            continue
        m = re.match(r"^framework\s*=\s*(.+)$", stripped, re.IGNORECASE)
        if m and framework in [f.strip() for f in m.group(1).split(",")]:
            return True
    return False


def extract_envs(ini_path: Path) -> list:
    envs = []
    seen = set()
    for m in re.finditer(r"^\[env:(.+?)\]", ini_path.read_text(), re.MULTILINE):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            envs.append(m.group(1))
    return envs


def localize_platform(ini_text: str, root: Path) -> str:
    """Rewrite repo platform URLs to the local checkout."""
    lines = []
    for line in ini_text.splitlines():
        m = re.match(r"^platform\s*=\s*(.+)$", line.strip())
        if m and any(m.group(1).startswith(pfx) for pfx in REPO_PLATFORM_PREFIXES):
            line = "platform = %s" % str(root)
        lines.append(line)
    return "\n".join(lines) + "\n"


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--framework", required=True,
        help="framework line to select projects by (arduino, zephyr, ...)")
    parser.add_argument(
        "--examples-dir", default="examples",
        help="directory holding the example projects (default: examples)")
    args = parser.parse_args(argv)

    root = repo_root()
    examples = (root / args.examples_dir).resolve()
    if not examples.is_dir():
        print("examples dir not found: %s" % examples, file=sys.stderr)
        return 2

    projects = [
        p for p in find_projects(examples)
        if uses_framework(p.joinpath("platformio.ini").read_text(), args.framework)
    ]
    if not projects:
        print("no %s projects found under %s" % (args.framework, examples),
              file=sys.stderr)
        return 2

    failures = []
    for project in projects:
        ini_text = project.joinpath("platformio.ini").read_text()
        conf = project / ".pio-ci.platformio.ini"
        conf.write_text(localize_platform(ini_text, root))
        try:
            for env in extract_envs(project / "platformio.ini"):
                rc = subprocess.run(
                    ["platformio", "run", "-d", str(project),
                     "--project-conf", str(conf), "-e", env],
                    cwd=str(root),
                ).returncode
                print("%s:%s -> %s" % (
                    project.name, env, "OK" if rc == 0 else "FAILED"), flush=True
                )
                if rc != 0:
                    failures.append("%s:%s" % (project.name, env))
        finally:
            conf.unlink(missing_ok=True)

    print("RESULT:", "ALL GREEN" if not failures else "FAILURES: %s" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
