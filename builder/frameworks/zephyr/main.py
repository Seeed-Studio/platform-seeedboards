# Copyright 2019-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
The Zephyr Project is a scalable real-time operating system (RTOS) supporting multiple
hardware architectures, optimized for resource constrained devices, and built with
safety and security in mind.

https://github.com/zephyrproject-rtos/zephyr
"""

from os.path import join
import subprocess
import glob
import os
import json
import shutil
import sys
from SCons.Script import Import, SConscript
try:
    import yaml
except ImportError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyyaml"],
        check=True,
    )
    import yaml

Import("env")

platform_name = env.subst("$PIOPLATFORM")
board_name = env.get("BOARD", "")
platform = env.PioPlatform()
framework_version = None

# The dispatchers (builder/main.py router, frameworks/arduino.py) keep
# this repo's root on sys.path, so the families registry import works
# here even while PioPlatform is wrapped (get_dir() = the upstream
# package for upstream-backed families). SCons deletes __file__ in
# SConscript frames, so host paths come from family.host_dir(), never
# from __file__ or get_dir().
from families import resolve_board_family

_family = resolve_board_family(env.BoardConfig(), board_name)
platform_dir = _family.host_dir()
# Canonical Zephyr board name (build.zephyr.variant's first component) —
# the one vocabulary for every board-specific gate below (module
# provisioning, fixes dispatch), never the PIO board id.
zephyr_board = platform.get_zephyr_board_name(board_name)

_zephyr_platform_override = _family.zephyr_pioplatform()
if _zephyr_platform_override:
    env.Replace(
        PIOPLATFORM=_zephyr_platform_override
    )
# Clone hal_nordic package from west.yaml if not present
framework_dir = platform.get_package_dir("framework-zephyr")

# Copy custom board definitions into Zephyr framework boards directory
# so that Zephyr CMake can discover them during build configuration.
# Note: We intentionally use copytree instead of symlink on all platforms.
# Python's pathlib.Path.rglob() (used by Zephyr's list_boards.py) does not
# follow symlink directories by default, which makes symlinked boards
# invisible to CMake on macOS/Linux.
# Board definitions live in per-family board roots: zephyr/<family>/boards/seeed/<board>.
# Each family root is a standalone Zephyr board root; adding a family requires no
# builder change (the glob below picks it up). zephyr/nrf is the root the wiki tells
# users to add to nRF Connect Board Roots, so it may only contain boards whose SoC and
# drivers exist unpatched in the target SDK — a board referencing a SoC missing from
# the SDK (e.g. xiao_stm32c5's stm32c5a3xx in NCS) breaks the extension's SoC cache
# for every board. Boards that depend on framework fixes belong in their own family
# root (zephyr/stm32) and reach the framework only through this copy step.
# glob() also returns files; a non-directory here would make os.listdir()
# below raise and kill every build, so keep directories only.
platform_board_source_roots = [p for p in sorted(glob.glob(
    join(platform_dir, "zephyr", "*", "boards", "*"))) if os.path.isdir(p)]
framework_boards_dir = join(framework_dir, "boards", "arm")
framework_vendor_boards_dir = join(framework_dir, "boards", "seeed")

def _get_framework_version():
    global framework_version
    if framework_version:
        return framework_version

    package_json = join(framework_dir, "package.json")
    with open(package_json, "r", encoding="utf-8") as fp:
        package_data = json.load(fp)

    raw_version = package_data.get("version", "")
    parts = raw_version.split(".")
    if len(parts) < 2 or not parts[1].isdigit():
        raise RuntimeError(
            f"Unexpected framework-zephyr version: {raw_version}"
        )

    encoded = parts[1].zfill(5)
    major = int(encoded[0])
    minor = int(encoded[1:3])
    patch = int(encoded[3:5])
    framework_version = f"{major}.{minor}.{patch}"
    return framework_version


def _board_copy_mode():
    # The framework package is persistent across PlatformIO projects. Refresh
    # every bundled board so changes in this platform package (DTS, pinctrl,
    # Kconfig, or board metadata) are not hidden by a stale framework copy.
    return "refresh"


if platform_board_source_roots:
    os.makedirs(framework_vendor_boards_dir, exist_ok=True)
    board_copy_mode = _board_copy_mode()
    for platform_boards_dir in platform_board_source_roots:
        for board_name_dir in os.listdir(platform_boards_dir):
            src = join(platform_boards_dir, board_name_dir)
            dst = join(framework_vendor_boards_dir, board_name_dir)
            stale_arm_dst = join(framework_boards_dir, board_name_dir)
            if not os.path.isdir(src):
                continue
            if os.path.isdir(stale_arm_dst):
                shutil.rmtree(stale_arm_dst)
            if board_copy_mode == "missing-only" and os.path.exists(dst):
                continue
            # Refresh copied board definitions on every build so local DTS/Kconfig
            # changes always override any stale board copies inside the framework.
            if os.path.islink(dst) and not os.path.exists(dst):
                os.remove(dst)
            elif os.path.isdir(dst):
                shutil.rmtree(dst)
            elif os.path.exists(dst):
                os.remove(dst)
            shutil.copytree(src, dst)
            print(f"Copied board: {board_name_dir} -> {dst}")

def _get_zephyr_venv_dir():
    return join(
        env.subst("$PROJECT_CORE_DIR"),
        "penv",
        ".zephyr-" + _get_framework_version(),
    )


def _clear_problematic_pip_cache():
    pip_cache = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "pip",
        "cache",
        "wheels",
    )
    if not os.path.isdir(pip_cache):
        return

    for root, _, files in os.walk(pip_cache):
        for name in files:
            if name.startswith("docopt-") and name.endswith(".whl"):
                try:
                    os.remove(os.path.join(root, name))
                except OSError:
                    pass


# Must stay equal to the engine's ZEPHYR_ENV_VERSION in the framework
# package's scripts/platformio/platformio-build.py ("1.0.0"): that script
# reads the same marker file after ours and RECREATES the venv whenever
# the version differs (wiping deps_sha and re-running its own pip). We
# only append our own deps_sha key, which the engine never touches.
VENV_DATA_VERSION = "1.0.0"


def _pinned_deps():
    deps = [
        "pyelftools~=0.27",
        "PyYAML~=6.0.0",
        "pykwalify~=1.8.0",
        "packaging~=23.1.0",
        "cryptography>=2.6.0",
        "intelhex~=2.3.0",
        "click~=8.1.3",
        "cbor2~=5.4.6",
        "jsonschema~=4.25.1",
    ]
    if os.name == "nt":
        deps.append("windows-curses")
    return deps


def _deps_digest(requirements, pinned):
    """Content digest of everything the two pip installs would install.

    Stored in the venv marker; unchanged digest = the venv is already
    provisioned and both pip subprocesses are skipped (each build used to
    spawn two pip runs even with nothing to do)."""
    import hashlib
    digest = hashlib.sha256()
    try:
        with open(requirements, "rb") as fp:
            digest.update(fp.read())
    except OSError:
        digest.update(b"<no-requirements>")
    for dep in pinned:
        digest.update(dep.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _ensure_zephyr_python_env():
    venv_dir = _get_zephyr_venv_dir()
    venv_data_file = join(venv_dir, "pio-zephyr-venv.json")
    python_exe = join(
        venv_dir,
        "Scripts" if os.name == "nt" else "bin",
        "python" + (".exe" if os.name == "nt" else ""),
    )

    requirements = join(framework_dir, "scripts", "requirements-base.txt")
    pinned_deps = _pinned_deps()
    deps_sha = _deps_digest(requirements, pinned_deps)

    venv_data = {}
    if os.path.isfile(venv_data_file):
        try:
            with open(venv_data_file, "r", encoding="utf-8") as fp:
                venv_data = json.load(fp)
        except Exception:
            venv_data = {}

    recreate = (
        not os.path.isfile(python_exe)
        or venv_data.get("version") != VENV_DATA_VERSION
    )
    if recreate:
        if os.path.isdir(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)
        subprocess.run(
            [env.subst("$PYTHONEXE"), "-m", "venv", "--clear", venv_dir],
            check=True,
        )
        os.makedirs(venv_dir, exist_ok=True)
        venv_data = {"version": VENV_DATA_VERSION}

    if not recreate and venv_data.get("deps_sha") == deps_sha:
        print("[zephyr-prep] venv dependencies unchanged, skipping pip")
        return

    def _save():
        venv_data["deps_sha"] = deps_sha
        with open(venv_data_file, "w", encoding="utf-8") as fp:
            json.dump(venv_data, fp, indent=2)

    _clear_problematic_pip_cache()
    subprocess.run(
        [
            python_exe,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "-r",
            requirements,
        ],
        check=True,
    )
    subprocess.run(
        [
            python_exe,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--disable-pip-version-check",
            *pinned_deps,
        ],
        check=True,
    )
    # Recorded only after both installs succeed -- a failed install leaves
    # the stale digest in the marker, so the next build re-runs pip instead
    # of skipping it with a half-provisioned venv.
    _save()


def _ensure_minimal_west_workspace(framework_dir):
    """Create the minimum west workspace metadata expected by Zephyr 4.4.

    PlatformIO installs the selected Zephyr framework package as a plain source tree, not as a
    `west init` workspace. Newer Zephyr tooling may still call
    `Manifest.from_file()` and expect a `.west/config` file to exist.
    """
    west_dir = join(framework_dir, ".west")
    west_config = join(west_dir, "config")

    if not os.path.isdir(west_dir):
        os.makedirs(west_dir, exist_ok=True)

    expected = "[manifest]\npath = .\nfile = west.yml\n"
    current = ""
    if os.path.isfile(west_config):
        with open(west_config, "r", encoding="utf-8") as fp:
            current = fp.read()

    if current != expected:
        with open(west_config, "w", encoding="utf-8") as fp:
            fp.write(expected)


def _preinstall_west_deps(framework_dir, platform_name_hint):
    """Pre-install west.yml dependencies with retry so that install-deps.py
    can skip them later. This avoids the clean_up() wiping everything on
    a single clone failure."""
    west_yml = join(framework_dir, "west.yml")
    if not os.path.isfile(west_yml):
        return

    pio_dir = join(framework_dir, "_pio")

    with open(west_yml, "r", encoding="utf-8") as f:
        west_data = yaml.safe_load(f)
    manifest = west_data.get("manifest", {})
    remotes = {r["name"]: r for r in manifest.get("remotes", [])}
    default_remote = manifest.get("defaults", {}).get("remote", "")

    hal_modules_by_platform = {
        "nordicnrf52": {"hal_nordic"},
        "nordicnrf51": {"hal_nordic"},
        "ststm32": {"hal_st", "hal_stm32"},
    }
    required_hal_modules = hal_modules_by_platform.get(platform_name_hint)
    if not required_hal_modules:
        return

    print("Pre-installing Zephyr west dependencies (with retry)...")

    for proj in manifest.get("projects", []):
        name = proj.get("name", "")
        proj_path = proj.get("path", name)

        # Skip tool packages
        if proj_path.startswith("tool") or name.startswith("nrf_hw_"):
            continue

        # Only install HAL packages needed by the selected platform. Core
        # west modules, including cmsis and cmsis_6, are installed normally.
        if name.startswith("hal_") and name not in required_hal_modules:
            continue

        dst = join(pio_dir, proj_path)
        if os.path.isdir(dst):
            continue

        # Build URL
        if "url" in proj:
            proj_url = proj["url"]
            if not proj_url.startswith("http"):
                url_base = remotes.get(
                    proj.get("remote", default_remote), {}
                ).get("url-base", "")
                proj_url = url_base.rstrip("/") + "/" + proj_url.lstrip("/")
        else:
            url_base = remotes.get(
                proj.get("remote", default_remote), {}
            ).get("url-base", "")
            repo_path = proj.get("repo-path", name)
            proj_url = url_base.rstrip("/") + "/" + repo_path + ".git"

        revision = proj.get("revision")
        print(f"Pre-installing: {name}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        git_clone_with_retry(proj_url, dst, revision)

    print("Pre-install complete.")


# Pre-install west dependencies with retry before platformio-build.py runs
# This ensures they exist when install-deps.py checks, avoiding its
# destructive clean_up() on any single failure.
sys.path.insert(0, join(platform_dir, "builder", "frameworks", "zephyr"))
from modules import git_clone_with_retry  # noqa: E402


# Environment preparation, as data: ordered, one (name, step) row each.
# Adding a step is a one-line diff; the printed [zephyr-prep] tags make
# build logs addressable per step, and each step stays independently
# testable. Steps take no arguments -- everything they need is already in
# module scope (env, framework_dir, ...).
PREP_STEPS = [
    ("zephyr-venv", _ensure_zephyr_python_env),
    ("west-workspace", lambda: _ensure_minimal_west_workspace(framework_dir)),
    ("west-deps", lambda: _preinstall_west_deps(
        framework_dir, env.subst("$PIOPLATFORM"))),
]

for step_name, step in PREP_STEPS:
    print("[zephyr-prep] %s" % step_name)
    step()

# Modules: every directory under zephyr/modules/ is provisioned through one
# generic path (vendored copy or pinned external clone, gated by its
# pin.yml) and registered via ZEPHYR_EXTRA_MODULES — Zephyr's official
# channel, which reaches sysbuild child images (mcuboot) as well. Adding a
# module = dropping a directory; nothing here changes.
from modules import provision  # noqa: E402

provision(platform_dir, framework_dir, zephyr_board,
          family_id=_family.family_ids[0] if _family.family_ids else "",
          project_dir=env.subst("$PROJECT_DIR"))

# Apply Zephyr fixes: framework level (zephyr/fixes/, engine patches) first,
# then this board's fixes under zephyr/<family>/boards/seeed/<board>/fixes/
# (directory convention, dispatched by fixes.py — boards without a
# fixes/ directory get no fixes, so there is no coupling across boards).
from fixes import apply_all  # noqa: E402

apply_all(platform_dir, framework_dir, zephyr_board,
          _get_framework_version())

SConscript(
    join(framework_dir, "scripts", "platformio", "platformio-build.py"), exports="env")

if _zephyr_platform_override:
    env.Replace(
        PIOPLATFORM=platform_name
    )
