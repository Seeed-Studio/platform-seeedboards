#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_PLATFORM_URL_PREFIXES = (
    "https://github.com/Seeed-Studio/platform-seeedboards",
    "git+https://github.com/Seeed-Studio/platform-seeedboards",
)


def repo_root() -> Path:
    # scripts/ci/* -> repo root
    return Path(__file__).resolve().parents[2]


def local_platform_spec() -> str:
    # PlatformIO accepts a local directory path as a platform spec.
    # Using file:// URIs on Windows can be mis-parsed into '/C:/...' and fail.
    root = repo_root().resolve()
    # IMPORTANT: On Windows, writing "C:/..." is ambiguous (looks like a URI scheme "c:")
    # and PlatformIO may normalize it into a broken file:/// URI. Use native paths.
    if os.name == "nt":
        return str(root)
    return root.as_posix()


def find_platformio_projects(examples_dir: Path) -> list[Path]:
    projects: list[Path] = []
    for ini_path in examples_dir.rglob("platformio.ini"):
        if ini_path.is_file():
            projects.append(ini_path.parent)
    return sorted(set(projects))


def project_category_prefix(project_relpath: Path) -> str | None:
    # project_relpath like: examples/zephyr-epaper/2inch13
    parts = project_relpath.parts
    if len(parts) < 2:
        return None
    if parts[0] != "examples":
        return None
    return parts[1]


def filter_projects_by_prefix(projects: list[Path], allowed_prefixes: tuple[str, ...]) -> list[Path]:
    root = repo_root()
    filtered: list[Path] = []
    for project_dir in projects:
        rel = project_dir.relative_to(root)
        cat = project_category_prefix(rel)
        if not cat:
            continue
        if any(cat.startswith(prefix) for prefix in allowed_prefixes):
            filtered.append(project_dir)
    return filtered


def project_uses_framework(project_dir: Path, framework: str) -> bool:
    """True if the project's platformio.ini selects the given framework.

    Reads the `framework =` line (case-insensitive, comma-separated). Selecting
    by framework content rather than by directory-name prefix covers board-grouped
    layouts like examples/seeed-xiao-stm32c5/zephyr-blink whose first path segment
    is the board name, not "zephyr-".
    """
    ini = project_dir / "platformio.ini"
    if not ini.is_file():
        return False
    text = ini.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        m = re.match(r"^framework\s*=\s*(.+?)\s*$", stripped, flags=re.IGNORECASE)
        if m:
            frameworks = [f.strip() for f in m.group(1).split(",")]
            return framework in frameworks
    return False


def filter_by_framework(projects: list[Path], framework: str) -> list[Path]:
    """Return projects whose platformio.ini selects the given framework.

    Replaces prefix-based filtering for framework-specific CI builds so new
    boards don't require a filter edit each time.
    """
    return [p for p in projects if project_uses_framework(p, framework)]


def should_override_platform(ini_text: str) -> bool:
    for line in ini_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            continue
        m = re.match(r"^platform\s*=\s*(.+?)\s*$", stripped, flags=re.IGNORECASE)
        if not m:
            continue
        value = m.group(1).strip()
        for prefix in REPO_PLATFORM_URL_PREFIXES:
            if value.startswith(prefix):
                return True
    return False


def can_use_local_platform_override() -> bool:
    # On native Windows (observed with PlatformIO Core 6.1.18 + Python 3.13),
    # installing a local platform from a filesystem path may result in an incomplete
    # package missing platform.json, which then fails with MissingPackageManifestError/UnknownPlatform.
    # CI runs on Linux, where local path overrides work reliably.
    if os.name == "nt":
        return False
    return True


def extract_env_names(ini_text: str) -> list[str]:
    envs: list[str] = []
    for line in ini_text.splitlines():
        m = re.match(r"^\s*\[\s*env:([^\]]+?)\s*\]\s*$", line, flags=re.IGNORECASE)
        if m:
            envs.append(m.group(1).strip())
    seen: set[str] = set()
    ordered: list[str] = []
    for env in envs:
        if env not in seen:
            ordered.append(env)
            seen.add(env)
    return ordered


def write_override_project_conf(project_dir: Path, ini_text: str, local_platform: str) -> Path:
    """Create a temporary PlatformIO config with repo platform URLs made local.

    PlatformIO loads ``extra_configs`` after the main configuration, so an
    override file that includes the original ``platformio.ini`` can let the
    original remote URL win.  Write a copy instead and replace matching platform
    URL values in place, preserving every other project setting.
    """
    override_path = project_dir / ".pio-ci.platformio.ini"
    platform_line = re.compile(
        r"^(?P<prefix>\s*platform\s*=\s*)(?P<value>.*?)(?P<suffix>\s*)$",
        flags=re.IGNORECASE,
    )
    lines: list[str] = []
    replaced = False
    for line in ini_text.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        content = line[:-1] if newline else line
        match = platform_line.match(content)
        if match and any(
            match.group("value").strip().startswith(prefix)
            for prefix in REPO_PLATFORM_URL_PREFIXES
        ):
            lines.append(
                f"{match.group('prefix')}{local_platform}{match.group('suffix')}{newline}"
            )
            replaced = True
        else:
            lines.append(line)

    if not replaced:
        raise RuntimeError("Unable to replace the repository platform URL in platformio.ini")
    override_path.write_text("".join(lines), encoding="utf-8")
    return override_path


def safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        # Best-effort cleanup; don't fail the build for temp file issues.
        pass


def _sanitize_filename(name: str) -> str:
    # Keep filenames portable across Windows/Linux/macOS.
    # Replace path separators and other non-filename characters.
    name = name.replace("/", "__").replace("\\", "__").replace(":", "_")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "log"


def _read_tail_lines(path: Path, n: int) -> list[str]:
    if n <= 0:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    lines = text.splitlines()
    return lines[-n:]


def run_build(
    project_dir: Path,
    env_name: str | None,
    project_conf: Path | None,
    override_platform_to_local: bool,
    verbose: bool,
    *,
    log_path: Path | None,
) -> int:
    cmd = ["platformio", "run", "-d", str(project_dir)]

    if project_conf is not None:
        cmd += ["--project-conf", str(project_conf)]

    if env_name:
        cmd += ["-e", env_name]

    # override_platform_to_local is handled via project_conf

    if verbose:
        print("+", " ".join(cmd), flush=True)

    env = os.environ.copy()
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("wb") as fp:
            proc = subprocess.run(cmd, cwd=str(repo_root()), env=env, stdout=fp, stderr=subprocess.STDOUT)
    else:
        proc = subprocess.run(cmd, cwd=str(repo_root()), env=env)
    return int(proc.returncode)


def build_projects(
    projects: list[Path],
    *,
    verbose: bool,
    log_dir: str | None,
    tail_lines: int,
    quiet: bool,
) -> int:
    failures: list[str] = []
    failure_logs: dict[str, Path] = {}
    root = repo_root()

    resolved_log_dir: Path | None = None
    if log_dir:
        resolved_log_dir = (root / log_dir).resolve()
        resolved_log_dir.mkdir(parents=True, exist_ok=True)

    for project_dir in projects:
        rel = project_dir.relative_to(root)
        ini_path = project_dir / "platformio.ini"
        ini_text = ini_path.read_text(encoding="utf-8", errors="replace")
        override = should_override_platform(ini_text) and can_use_local_platform_override()
        envs = extract_env_names(ini_text)

        override_conf: Path | None = None
        try:
            if override:
                override_conf = write_override_project_conf(project_dir, ini_text, local_platform_spec())

            if not quiet:
                print("\n=== Building", str(rel), "===", flush=True)
                if should_override_platform(ini_text) and not override:
                    print("(note) local platform override disabled on this host", flush=True)
                elif override:
                    print("(CI override) platform -> local repo", flush=True)

            if not envs:
                log_path: Path | None = None
                failure_key = f"{rel} (default)"
                if resolved_log_dir is not None:
                    log_name = _sanitize_filename(f"{rel}__default.log")
                    log_path = resolved_log_dir / log_name
                rc = run_build(
                    project_dir,
                    env_name=None,
                    project_conf=override_conf,
                    override_platform_to_local=override,
                    verbose=verbose,
                    log_path=log_path,
                )
                if rc != 0:
                    failures.append(f"{rel} (exit {rc})")
                    if log_path is not None:
                        failure_logs[failure_key] = log_path
                        if tail_lines > 0:
                            tail = _read_tail_lines(log_path, tail_lines)
                            if tail:
                                print(f"\n--- tail ({tail_lines} lines) {log_path} ---", file=sys.stderr)
                                for line in tail:
                                    print(line, file=sys.stderr)
                continue

            for env in envs:
                if not quiet:
                    print(f"--- env: {env} ---", flush=True)

                log_path = None
                failure_key = f"{rel}::{env}"
                if resolved_log_dir is not None:
                    log_name = _sanitize_filename(f"{rel}__{env}.log")
                    log_path = resolved_log_dir / log_name
                rc = run_build(
                    project_dir,
                    env_name=env,
                    project_conf=override_conf,
                    override_platform_to_local=override,
                    verbose=verbose,
                    log_path=log_path,
                )
                if rc != 0:
                    failures.append(f"{rel}::{env} (exit {rc})")
                    if log_path is not None:
                        failure_logs[failure_key] = log_path
                        if tail_lines > 0:
                            tail = _read_tail_lines(log_path, tail_lines)
                            if tail:
                                print(f"\n--- tail ({tail_lines} lines) {log_path} ---", file=sys.stderr)
                                for line in tail:
                                    print(line, file=sys.stderr)
        finally:
            if override_conf is not None:
                safe_unlink(override_conf)

    if failures:
        print("\nBuild failures:", file=sys.stderr)
        for item in failures:
            print("-", item, file=sys.stderr)
        if failure_logs:
            print("\nFailure logs:", file=sys.stderr)
            for key, path in sorted(failure_logs.items()):
                print(f"- {key}: {path}", file=sys.stderr)
        return 1

    print("\nAll selected example projects built successfully.")
    return 0


def make_argparser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--examples-dir", default="examples", help="Examples directory (default: examples)")
    parser.add_argument("--list", action="store_true", help="List detected projects and exit")
    parser.add_argument("--verbose", action="store_true", help="Print executed commands")
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Write full build logs to this directory (relative to repo root). If omitted, logs go to console.",
    )
    parser.add_argument(
        "--tail",
        type=int,
        default=120,
        help="On failure, print last N lines from the log file (default: 120; 0 to disable)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce console output (recommended with --log-dir)",
    )
    return parser
