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

# Symlink custom board definitions into Zephyr framework boards directory
# so that Zephyr CMake can discover them during build configuration.
platform_boards_dir = join(platform_dir, "zephyr", "boards", "arm")
framework_boards_dir = join(framework_dir, "boards", "arm")

if os.path.isdir(platform_boards_dir):
    os.makedirs(framework_boards_dir, exist_ok=True)
    for board_name_dir in os.listdir(platform_boards_dir):
        src = join(platform_boards_dir, board_name_dir)
        dst = join(framework_boards_dir, board_name_dir)
        if not os.path.isdir(src):
            continue
        if os.path.exists(dst) or os.path.islink(dst):
            continue
        try:
            os.symlink(src, dst)
            print(f"Linked board: {board_name_dir} -> {src}")
        except OSError:
            import shutil
            shutil.copytree(src, dst)
            print(f"Copied board: {board_name_dir} -> {dst}")

if not os.path.exists(hal_nordic_dir) and os.path.exists(west_yml_path):
    with open(west_yml_path, "r", encoding="utf-8") as f:
        west_data = yaml.safe_load(f)
    manifest = west_data.get("manifest", {})
    remotes = manifest.get("remotes", [])
    default_remote = manifest.get("defaults", {}).get("remote", "")
    url_base = next((r.get("url-base", "") for r in remotes if r.get("name") == default_remote), "")
    hal_nordic_url = None
    hal_nordic_rev = None
    for proj in manifest.get("projects", []):
        if proj.get("name") == "hal_nordic":
            proj_url = proj.get("url")
            if proj_url:
                if proj_url.startswith("http://") or proj_url.startswith("https://"):
                    hal_nordic_url = proj_url
                else:
                    hal_nordic_url = url_base.rstrip("/") + "/" + proj_url.lstrip("/")
            else:
                hal_nordic_url = url_base.rstrip("/") + "/hal_nordic.git"
            hal_nordic_rev = proj.get("revision")
            break
    if hal_nordic_url:
        print(f"Cloning hal_nordic from {hal_nordic_url} into {hal_nordic_dir}")
        subprocess.run(["git", "clone", hal_nordic_url, hal_nordic_dir], check=True)
        if hal_nordic_rev:
            subprocess.run(["git", "-C", hal_nordic_dir, "checkout", hal_nordic_rev], check=True)

SConscript(
    join(framework_dir, "scripts", "platformio", "platformio-build.py"), exports="env")
    
if board_name and "nrf" in board_name:
    env.Replace(
        PIOPLATFORM=platform_name
    )