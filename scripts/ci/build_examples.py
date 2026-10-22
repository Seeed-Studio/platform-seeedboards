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
    return sorted({
        p.parent for p in examples_dir.rglob("platformio.ini")
        if ".pio" not in p.parts
    })


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
    for m in re.finditer(r"^\[env:(.+?)\]", ini_path.read_text(encoding="utf-8"),
                         re.MULTILINE):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            envs.append(m.group(1))
    return envs


def select_envs(envs, only_envs) -> list:
    if not only_envs:
        return list(envs)
    wanted = set(only_envs)
    return [env for env in envs if env in wanted]


def localize_platform(ini_text: str, root: Path) -> str:
    """Rewrite repo platform URLs to the local checkout."""
    lines = []
    for line in ini_text.splitlines():
        m = re.match(r"^platform\s*=\s*(.+)$", line.strip())
        if m and any(m.group(1).startswith(pfx) for pfx in REPO_PLATFORM_PREFIXES):
            line = "platform = %s" % str(root)
        lines.append(line)
    return "\n".join(lines) + "\n"


def has_repo_platform(ini_text: str) -> bool:
    """True when every platform= line points at this repository."""
    values = []
    for line in ini_text.splitlines():
        m = re.match(r"^platform\s*=\s*(.+)$", line.strip())
        if m:
            values.append(m.group(1).strip())
    return bool(values) and all(
        any(value.startswith(pfx) for pfx in REPO_PLATFORM_PREFIXES)
        for value in values
    )


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--framework", required=True,
        help="framework line to select projects by (arduino, zephyr, ...)")
    parser.add_argument(
        "--examples-dir", default="examples",
        help="directory holding the example projects (default: examples)")
    parser.add_argument(
        "--log-dir", default=None,
        help="write one log per env under this directory (CI artifact)")
    parser.add_argument(
        "--clean", action="store_true",
        help="run `pio run -t clean` before each env (local T1)")
    parser.add_argument(
        "--only-env", action="append", default=[], metavar="ENV",
        help="build only this env (repeatable; across demo projects)")
    parser.add_argument(
        "--platform-dir", default=None,
        help="platform checkout written into the generated project conf "
             "(default: this repository; useful with a clean core dir)")
    args = parser.parse_args(argv)

    root = repo_root()
    examples = (root / args.examples_dir).resolve()
    if not examples.is_dir():
        print("examples dir not found: %s" % examples, file=sys.stderr)
        return 2

    log_dir = (root / args.log_dir).resolve() if args.log_dir else None
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

    projects = [
        p for p in find_projects(examples)
        if uses_framework(p.joinpath("platformio.ini").read_text(encoding="utf-8"),
                          args.framework)
    ]
    if not projects:
        print("no %s projects found under %s" % (args.framework, examples),
              file=sys.stderr)
        return 2

    platform_root = (Path(args.platform_dir).resolve()
                     if args.platform_dir else root)
    only_envs = set(args.only_env)
    failures = []
    selected = 0
    passed = 0
    for project in projects:
        ini_text = project.joinpath("platformio.ini").read_text(encoding="utf-8")
        if not has_repo_platform(ini_text):
            print("%s: platform URL is not the maintained repository"
                  % project.name, file=sys.stderr)
            failures.append("%s:platform-url" % project.name)
            continue
        envs = select_envs(extract_envs(project / "platformio.ini"), only_envs)
        if not envs:
            continue
        conf = project / ".pio-ci.platformio.ini"
        conf.write_text(localize_platform(ini_text, platform_root), encoding="utf-8")
        try:
            for env in envs:
                selected += 1
                log_path = None
                log_file = None
                if log_dir:
                    safe_project = project.relative_to(examples).as_posix().replace(
                        "/", "_")
                    log_path = log_dir / ("%s__%s.log" % (safe_project, env))
                    log_file = open(log_path, "w", encoding="utf-8")
                try:
                    kwargs = {"cwd": str(root)}
                    if log_file:
                        kwargs["stdout"] = log_file
                        kwargs["stderr"] = subprocess.STDOUT
                    cmd = ["platformio", "run", "-d", str(project),
                           "--project-conf", str(conf), "-e", env]
                    clean_rc = 0
                    if args.clean:
                        clean_rc = subprocess.run(
                            cmd + ["-t", "clean"], **kwargs).returncode
                    rc = clean_rc if clean_rc else subprocess.run(
                        cmd, **kwargs).returncode
                finally:
                    if log_file:
                        log_file.close()
                print("%s:%s -> %s%s" % (
                    project.name, env, "OK" if rc == 0 else "FAILED",
                    (" (log: %s)" % log_path) if rc != 0 and log_path else "",
                ), flush=True)
                if rc == 0:
                    passed += 1
                else:
                    failures.append("%s:%s" % (project.name, env))
        finally:
            conf.unlink(missing_ok=True)

    if selected == 0:
        print("no env matched --only-env %s" % sorted(only_envs),
              file=sys.stderr)
        return 2
    print("RESULT: %s (%d/%d envs)" % (
        "ALL GREEN" if not failures else "FAILURES: %s" % failures,
        passed, selected))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
