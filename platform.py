# Copyright 2014-present PlatformIO <contact@platformio.org>
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
#
# Attribution:
# ESP32-related package/toolchain selection logic in this repository is
# based in part on pioarduino project work:
# https://github.com/pioarduino/platform-espressif32
# Modified by Seeed Studio.

import os
import subprocess
import sys
from pathlib import Path

from platformio.public import PlatformBase, to_unix_path
from importlib import import_module
from platformio.package.manager.tool import ToolPackageManager
from platformio.proc import get_pythonexe_path
from platformio.project.config import ProjectConfig



IS_WINDOWS = sys.platform.startswith("win")
# Set Platformio env var to use windows_amd64 for all windows architectures
# only windows_amd64 native espressif toolchains are available
# needs platformio core >= 6.1.16b2 or pioarduino core 6.1.16+test
if IS_WINDOWS:
    os.environ["PLATFORMIO_SYSTEM_TYPE"] = "windows_amd64"

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

Architecture = ""

class SeeedstudioPlatform(PlatformBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._esp_tools_prepared = False

    def configure_default_packages(self, variables, targets):

        global Architecture
        if not variables.get("board"):
            return super().configure_default_packages(variables, targets)

        board_name = variables.get("board")

        if "esp32" in board_name:
            Architecture = "esp"
        if board_name == "seeed-xiao-ra4m1":
            Architecture = "renesas"
        if board_name == "seeed-xiao-rp2040" or board_name == "seeed-xiao-rp2350":
            Architecture = "rpi"
        if "nrf" in board_name:
            Architecture = "nrf"
        if "samd" in board_name:
            Architecture = "samd"
        if "mg24" in board_name:
            Architecture = "siliconlab"

        if Architecture:
            try:
                board_module = import_module(f"platform_cfg.{Architecture}_cfg")
                configure_board = getattr(board_module, f"configure_{Architecture}_default_packages")
                configure_board(self, variables, targets)
            except (ImportError, AttributeError) as e:

                print(f"Error: {e} for board {board_name}")

        if Architecture == "esp":
            self._prefer_local_esp_tools()

        result = super().configure_default_packages(variables, targets)

        if Architecture == "esp" and self._prepare_esp_tools():
            result = super().configure_default_packages(variables, targets)

        return result

    def _iter_required_esp_tools(self):
        return [
            name
            for name, options in self.packages.items()
            if name != "tool-esp_install"
            and name.startswith(("tool-", "toolchain-"))
            and not options.get("optional", True)
        ]

    def _prefer_local_esp_tools(self):
        packages_dir = Path(self._get_packages_dir())
        if not packages_dir.exists():
            return

        for tool_name in self._iter_required_esp_tools():
            pkg_meta = packages_dir / tool_name / "package.json"
            if pkg_meta.exists() and tool_name in self.packages:
                self.packages[tool_name]["version"] = str(packages_dir / tool_name)
                self.packages[tool_name]["optional"] = False

    def _prepare_esp_tools(self):
        if self._esp_tools_prepared:
            return False

        packages_dir = Path(self._get_packages_dir())
        core_dir = Path(self._get_core_dir())
        if not packages_dir.exists() or not core_dir.exists():
            return False

        self._ensure_esp_installer(packages_dir)

        changed = False
        for tool_name in self._iter_required_esp_tools():
            if self._expand_and_link_esp_tool(tool_name, packages_dir, core_dir):
                changed = True

        self._esp_tools_prepared = True
        return changed

    def _get_packages_dir(self):
        config = ProjectConfig.get_instance()
        return config.get("platformio", "packages_dir")

    def _get_core_dir(self):
        config = ProjectConfig.get_instance()
        return config.get("platformio", "core_dir")

    def _ensure_esp_installer(self, packages_dir):
        installer = packages_dir / "tool-esp_install" / "tools" / "idf_tools.py"
        if installer.exists():
            return

        package_data = self.packages.get("tool-esp_install", {})
        version = package_data.get("version")
        if not version:
            return

        try:
            ToolPackageManager().install(version)
        except Exception as e:
            print(f"Warning: failed to install tool-esp_install: {e}")

    def _expand_and_link_esp_tool(self, tool_name, packages_dir, core_dir):
        pkg_dir = packages_dir / tool_name
        tools_json = pkg_dir / "tools.json"
        if not tools_json.exists():
            return False

        installer = packages_dir / "tool-esp_install" / "tools" / "idf_tools.py"
        core_tool_dir = core_dir / "tools" / tool_name

        if not (core_tool_dir / "package.json").exists():
            if not installer.exists():
                print(f"Warning: idf_tools.py not found, cannot expand {tool_name}")
                return False

            cmd = [
                get_pythonexe_path(),
                str(installer),
                "--quiet",
                "--non-interactive",
                "--tools-json",
                str(tools_json),
                "install",
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "").strip()[-1000:]
                print(f"Warning: failed to expand {tool_name} via idf_tools.py: {tail}")
                return False

        if not (core_tool_dir / "package.json").exists():
            return False

        changed = False
        try:
            pkg_meta = pkg_dir / "package.json"
            if not pkg_meta.exists():
                ToolPackageManager().install(f"file://{core_tool_dir}")
                changed = True

            if tool_name in self.packages:
                linked_version = str(packages_dir / tool_name)
                if self.packages[tool_name].get("version") != linked_version:
                    changed = True
                self.packages[tool_name]["version"] = str(packages_dir / tool_name)
                self.packages[tool_name]["optional"] = False
        except Exception as e:
            print(f"Warning: failed to link expanded tool {tool_name}: {e}")
            return False

        return changed


    def get_boards(self, id_=None):
        result = super().get_boards(id_)
        if not result:
            return result
        if id_:
            return self._add_dynamic_options(result)
        else:
            for key in result:
                result[key] = self._add_dynamic_options(result[key])
        return result


    def _add_dynamic_options(self, board):
        global Architecture
        board_name = board.id
        if "esp32" in board_name:
            Architecture = "esp"
        if board_name == "seeed-xiao-ra4m1":
            Architecture = "renesas"

        if board_name == "seeed-xiao-rp2040" or board_name == "seeed-xiao-rp2350":
            Architecture = "rpi"

        if "nrf" in board_name:
            Architecture = "nrf"
        if "samd" in board_name:
            Architecture = "samd"
        if "mg24" in board_name:
            Architecture = "siliconlab"

        if Architecture:
            # 动态导入板子配置函数
            try:
                board_module = import_module(f"platform_cfg.{Architecture}_cfg")
                configure_tool = getattr(board_module, f"_add_{Architecture}_default_debug_tools")
                return configure_tool(self, board)
            except (ImportError, AttributeError) as e:
                print(f"Error: in _add_dynamic_options {e} for board {board_name}")
        else:
            print("no config Architecture")
            return



    def configure_debug_session(self, debug_config):
        global Architecture

        if Architecture:
            # 动态导入板子配置函数
            try:
                board_module = import_module(f"platform_cfg.{Architecture}_cfg")
                configure_debug_seesion = getattr(board_module, f"configure_{Architecture}_debug_session")
                configure_debug_seesion(self, debug_config)
            except (ImportError, AttributeError) as e:
                print(f"Error: in configure_debug_session {e} for board {Architecture}")
