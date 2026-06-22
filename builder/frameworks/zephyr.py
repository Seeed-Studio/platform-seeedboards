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
from SCons.Script import Import, SConscript
try:
    import yaml
except ImportError:
    subprocess.run(["pip", "install", "pyyaml"], check=True)
    import yaml

Import("env")

platform_name = env.subst("$PIOPLATFORM")
board_name = env.get("BOARD", "")

if board_name and "nrf" in board_name:
    env.Replace(
        PIOPLATFORM="nordicnrf52"
    )

# Clone hal_nordic package from west.yaml if not present
framework_dir = env.PioPlatform().get_package_dir("framework-zephyr")
platform_dir = env.PioPlatform().get_dir()
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

if os.path.isdir(platform_boards_dir):
    os.makedirs(framework_boards_dir, exist_ok=True)
    import shutil
    for board_name_dir in os.listdir(platform_boards_dir):
        src = join(platform_boards_dir, board_name_dir)
        dst = join(framework_boards_dir, board_name_dir)
        if not os.path.isdir(src):
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


def _patch_platformio_path_handling(framework_dir):
    """Make PlatformIO's Zephyr env keep the system PATH when appending tools."""
    build_py = join(framework_dir, "scripts", "platformio", "platformio-build.py")
    if not os.path.isfile(build_py):
        return

    with open(build_py, "r", encoding="utf-8") as fp:
        text = fp.read()

    needle = '    zephyr_env["PATH"] = os.pathsep.join(additional_packages)\n'
    replacement = (
        '    zephyr_env["PATH"] = os.pathsep.join(\n'
        '        additional_packages + [zephyr_env.get("PATH", "")]\n'
        '    )\n'
    )

    if needle in text and replacement not in text:
        text = text.replace(needle, replacement)
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
_preinstall_west_deps(framework_dir, env.subst("$PIOPLATFORM"))
_patch_platformio_path_handling(framework_dir)

SConscript(
    join(framework_dir, "scripts", "platformio", "platformio-build.py"), exports="env")
    
if board_name and "nrf" in board_name:
    env.Replace(
        PIOPLATFORM=platform_name
    )
