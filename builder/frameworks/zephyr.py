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
import os
import json
import shutil
from SCons.Script import Import, SConscript
try:
    import yaml
except ImportError:
    subprocess.run(["pip", "install", "pyyaml"], check=True)
    import yaml

Import("env")

platform_name = env.subst("$PIOPLATFORM")
board_name = env.get("BOARD", "")
platform = env.PioPlatform()
framework_package_name = platform.get_zephyr_package_name(board_name)
framework_version = None

if board_name and "nrf" in board_name:
    env.Replace(
        PIOPLATFORM="nordicnrf52"
    )
# Clone hal_nordic package from west.yaml if not present
framework_dir = platform.get_package_dir(framework_package_name)
platform_dir = platform.get_dir()
west_yml_path = join(framework_dir, "west.yml")
hal_nordic_dir = join(framework_dir, "_pio", "modules", "hal", "nordic")

# Copy custom board definitions into Zephyr framework boards directory
# so that Zephyr CMake can discover them during build configuration.
# Note: We intentionally use copytree instead of symlink on all platforms.
# Python's pathlib.Path.rglob() (used by Zephyr's list_boards.py) does not
# follow symlink directories by default, which makes symlinked boards
# invisible to CMake on macOS/Linux.
platform_boards_dir = join(platform_dir, "zephyr", "boards", "arm")
framework_boards_dir = join(framework_dir, "boards", "arm")

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
            f"Unexpected {framework_package_name} version: {raw_version}"
        )

    encoded = parts[1].zfill(5)
    major = int(encoded[0])
    minor = int(encoded[1:3])
    patch = int(encoded[3:5])
    framework_version = f"{major}.{minor}.{patch}"
    return framework_version


def _board_copy_mode():
    version = _get_framework_version()
    try:
        major, minor, _patch = [int(part) for part in version.split(".")]
    except ValueError:
        return "refresh"

    if (major, minor) >= (4, 4):
        return "missing-only"
    return "refresh"


if os.path.isdir(platform_boards_dir):
    os.makedirs(framework_boards_dir, exist_ok=True)
    import shutil
    board_copy_mode = _board_copy_mode()
    for board_name_dir in os.listdir(platform_boards_dir):
        src = join(platform_boards_dir, board_name_dir)
        dst = join(framework_boards_dir, board_name_dir)
        if not os.path.isdir(src):
            continue
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

import re
import time


def _ensure_system_path_available():
    """Keep system tools like git available for west/zephyr helper scripts."""
    current_path = os.environ.get("PATH", "")
    if current_path:
        os.environ["PATH"] = current_path


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


def _ensure_zephyr_python_env():
    venv_dir = _get_zephyr_venv_dir()
    venv_data_file = join(venv_dir, "pio-zephyr-venv.json")
    python_exe = join(
        venv_dir,
        "Scripts" if os.name == "nt" else "bin",
        "python" + (".exe" if os.name == "nt" else ""),
    )

    recreate = not os.path.isfile(python_exe)
    if not recreate and os.path.isfile(venv_data_file):
        try:
            with open(venv_data_file, "r", encoding="utf-8") as fp:
                venv_data = json.load(fp)
            recreate = venv_data.get("version") != "1.0.0"
        except Exception:
            recreate = True
    elif not os.path.isfile(venv_data_file):
        recreate = True

    if recreate:
        if os.path.isdir(venv_dir):
            shutil.rmtree(venv_dir, ignore_errors=True)
        subprocess.run(
            [env.subst("$PYTHONEXE"), "-m", "venv", "--clear", venv_dir],
            check=True,
        )
        os.makedirs(venv_dir, exist_ok=True)
        with open(venv_data_file, "w", encoding="utf-8") as fp:
            json.dump({"version": "1.0.0"}, fp, indent=2)

    requirements = join(framework_dir, "scripts", "requirements-base.txt")
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
    pinned_deps = [
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
        pinned_deps.append("windows-curses")
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


def _patch_platformio_path_handling(framework_dir):
    """Make PlatformIO's Zephyr env keep the system PATH and robust pip flags."""
    build_py = join(framework_dir, "scripts", "platformio", "platformio-build.py")
    if not os.path.isfile(build_py):
        return

    with open(build_py, "r", encoding="utf-8") as fp:
        text = fp.read()

    replacements = {
        '    zephyr_env["PATH"] = os.pathsep.join(additional_packages)\n': (
            '    zephyr_env["PATH"] = os.pathsep.join(\n'
            '        additional_packages + [zephyr_env.get("PATH", "")]\n'
            '    )\n'
        ),
        '"%s" -m pip install windows-curses': (
            '"%s" -m pip install --no-cache-dir --disable-pip-version-check windows-curses'
        ),
        '"%s" -m pip install -U ': (
            '"%s" -m pip install --no-cache-dir --disable-pip-version-check -U '
        ),
    }

    for needle, replacement in replacements.items():
        if needle in text and replacement not in text:
            text = text.replace(needle, replacement)

    with open(build_py, "w", encoding="utf-8") as fp:
        fp.write(text)


def _patch_platformio_object_naming(framework_dir):
    """Disambiguate duplicate source basenames inside framework modules.

    Zephyr 4.4's LVGL tree contains duplicate vg_lite_matrix.c files in
    different folders. PlatformIO's stock object naming can collapse them to
    the same .o target. Restrict the workaround to duplicate basenames only.
    """
    build_py = join(framework_dir, "scripts", "platformio", "platformio-build.py")
    if not os.path.isfile(build_py):
        return

    with open(build_py, "r", encoding="utf-8") as fp:
        text = fp.read()

    old_else = """            else:\n                obj_path = os.path.join(\n                    obj_path_temp, os.path.basename(src_path)\n                )\n"""
    new_else = """            else:\n                base_name = os.path.basename(src_path)\n                if base_name in duplicate_basenames:\n                    framework_root = FRAMEWORK_DIR\n                    if src_path.startswith(framework_root):\n                        unique_rel = os.path.relpath(src_path, framework_root)\n                    else:\n                        unique_rel = os.path.join(\n                            os.path.basename(os.path.dirname(src_path)),\n                            base_name,\n                        )\n                    obj_path = os.path.join(obj_path_temp, unique_rel)\n                else:\n                    obj_path = os.path.join(obj_path_temp, base_name)\n"""

    changed = False
    header_pattern = re.compile(
        r"def compile_source_files\(\n"
        r"\s+config, default_env, project_src_dir, prepend_dir=None\n"
        r"\):\n"
        r"\s+build_envs = prepare_build_envs\(config, default_env\)\n"
        r"\s+objects = \[\]\n"
        r"\s+for source in config\.get\(\"sources\", \[\]\):\n"
    )
    header_replacement = (
        "def compile_source_files(\n"
        "    config, default_env, project_src_dir, prepend_dir=None\n"
        "):\n"
        "    build_envs = prepare_build_envs(config, default_env)\n"
        "    objects = []\n"
        "    duplicate_basenames = set()\n"
        "    basename_count = {}\n"
        "    for source in config.get(\"sources\", []):\n"
        "        source_path = source.get(\"path\")\n"
        "        if not source_path or source_path.endswith(\".rule\"):\n"
        "            continue\n"
        "        if not os.path.isabs(source_path):\n"
        "            source_path = os.path.join(PROJECT_DIR, \"zephyr\", source_path)\n"
        "        base = os.path.basename(source_path)\n"
        "        basename_count[base] = basename_count.get(base, 0) + 1\n"
        "    duplicate_basenames = {k for k, v in basename_count.items() if v > 1}\n"
        "    for source in config.get(\"sources\", []):\n"
    )

    if "duplicate_basenames = set()" not in text:
        text, count = header_pattern.subn(header_replacement, text, count=1)
        changed = changed or count > 0
    if old_else in text and new_else not in text:
        text = text.replace(old_else, new_else)
        changed = True
    if changed:
        with open(build_py, "w", encoding="utf-8") as fp:
            fp.write(text)


def _is_commit_hash(value):
    return value and re.match(r"[0-9a-f]{7,}$", value) is not None


def _git_clone_with_retry(url, dst, revision, max_retries=3, retry_delay=5):
    """Clone a git repository with retry logic for unstable networks."""
    for attempt in range(1, max_retries + 1):
        args = ["git", "clone"]
        is_commit = _is_commit_hash(revision)
        if not is_commit and revision:
            args.extend(["--branch", revision, "--depth", "1"])
        elif not is_commit:
            args.extend(["--depth", "1"])

        try:
            print(f"  Cloning {url} (attempt {attempt}/{max_retries})")
            subprocess.run(args + [url, dst], check=True,
                           capture_output=True, text=True)
            if is_commit and revision:
                subprocess.run(
                    ["git", "-C", dst, "checkout", revision],
                    check=True, capture_output=True, text=True)
            print(f"  OK: {os.path.basename(dst)}")
            return True
        except subprocess.CalledProcessError as e:
            if os.path.isdir(dst):
                import shutil
                shutil.rmtree(dst, ignore_errors=True)
            if attempt < max_retries:
                print(f"  Failed (attempt {attempt}): {e.stderr.strip() if e.stderr else e}")
                print(f"  Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"  FAILED after {max_retries} attempts: {url}")
                return False
    return False


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

    # Only pre-install for platforms that need hal_nordic (nordicnrf52, etc.)
    hal_platforms = {"nordicnrf52", "nordicnrf51"}
    if platform_name_hint not in hal_platforms:
        return

    print("Pre-installing Zephyr west dependencies (with retry)...")

    for proj in manifest.get("projects", []):
        name = proj.get("name", "")
        proj_path = proj.get("path", name)

        # Skip tool packages
        if proj_path.startswith("tool") or name.startswith("nrf_hw_"):
            continue

        # Only install HAL packages needed for nordic
        if name.startswith("hal_") and name != "hal_nordic":
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
        _git_clone_with_retry(proj_url, dst, revision)

    print("Pre-install complete.")


# Pre-install west dependencies with retry before platformio-build.py runs
# This ensures they exist when install-deps.py checks, avoiding its
# destructive clean_up() on any single failure.
_ensure_system_path_available()
_ensure_zephyr_python_env()
_ensure_minimal_west_workspace(framework_dir)
_preinstall_west_deps(framework_dir, env.subst("$PIOPLATFORM"))
_patch_platformio_path_handling(framework_dir)
_patch_platformio_object_naming(framework_dir)

SConscript(
    join(framework_dir, "scripts", "platformio", "platformio-build.py"), exports="env")
    
if board_name and "nrf" in board_name:
    env.Replace(
        PIOPLATFORM=platform_name
    )
