#!/usr/bin/env python3

from __future__ import annotations

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


def main() -> int:
    root = repo_root()
    examples = root / "examples"
    if not examples.is_dir():
        print("no examples/ dir", file=sys.stderr)
        return 2

    projects = [
        p for p in find_projects(examples)
        if uses_framework(p.joinpath("platformio.ini").read_text(), "arduino")
    ]
    if not projects:
        print("no arduino projects found", file=sys.stderr)
        return 2

    failures = []
    for project in projects:
        ini_text = project.joinpath("platformio.ini").read_text()
        conf = project / ".pio-ci.platformio.ini"
        conf.write_text(ini_text)
        # rewrite platform lines to the local checkout
        lines = []
        for line in ini_text.splitlines():
            m = re.match(r"^platform\s*=\s*(.+)$", line.strip())
            if m and any(m.group(1).startswith(pfx) for pfx in REPO_PLATFORM_PREFIXES):
                line = "platform = %s" % str(root)
            lines.append(line)
        conf.write_text("\n".join(lines) + "\n")
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
