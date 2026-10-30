# Copyright 2026-present Seeed Studio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""STM32 chip family (STM32C5, Zephyr).

Local-keep: STM32C5 does not exist in platformio/platform-ststm32 (no
board, package, or builder reference), so this family keeps its local
builder scripts — builder/families/stm32/stm32_build.py is the board
level skeleton and the UF2/stlink upload chain stays untouched. The
package matrix and the default debug-tools table are inlined from the
retired platform_cfg/stm32_cfg.py; Zephyr builds ride the unified
framework-zephyr package via the framework's own script.

Package notes: Zephyr builds pin toolchain-gccarmnoneeabi to ~1.120301.0
(framework-zephyr 4.4 needs the asm "inline" qualifier, GCC >= 9 — the
same pin upstream ststm32 uses for Zephyr) plus the tool-cmake /
tool-dtc / tool-ninja (and non-Windows tool-gperf) build tools.
"""

import sys
from os.path import join

from .base import ChipFamily

IS_WINDOWS = sys.platform.startswith("win")


class Stm32Family(ChipFamily):
    family_ids = ("stm32",)
    owned_packages = ("tool-jlink",)

    # -- package matrix --------------------------------------------------

    def configure_default_packages(self, platform, variables, targets):
        board = variables.get("board")
        frameworks = variables.get("pioframework", [])

        if board:
            platform.packages["toolchain-gccarmnoneeabi"]["optional"] = False

            if "zephyr" in frameworks:
                for package_name in ("tool-cmake", "tool-dtc", "tool-ninja"):
                    platform.packages[package_name]["optional"] = False
                # framework-zephyr 4.4 needs the asm "inline" qualifier
                # (GCC >= 9); 12.3 is what upstream ststm32 pins for Zephyr.
                platform.packages["toolchain-gccarmnoneeabi"]["version"] = (
                    "~1.120301.0"
                )
                if not IS_WINDOWS:
                    platform.packages["tool-gperf"]["optional"] = False

        jlink_requested = any(
            "jlink" in variables.get(option, "")
            for option in ("upload_protocol", "debug_tool")
        )
        if board:
            board_config = platform.board_config(board)
            jlink_requested = jlink_requested or any(
                "jlink" in board_config.get(key, "")
                for key in ("debug.default_tools", "upload.protocol")
            )
        if not jlink_requested and "tool-jlink" in platform.packages:
            self.drop_package(platform, "tool-jlink")

    # -- debug -----------------------------------------------------------

    def add_default_debug_tools(self, platform, board):
        debug = board.manifest.setdefault("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get("protocols", [])
        debug_tools = debug.setdefault("tools", {})

        if "stlink" not in upload_protocols or "stlink" in debug_tools:
            return board

        openocd_target = debug.get("openocd_target")
        server_args = [
            "-s", "$PACKAGE_DIR/openocd/scripts",
            "-f", "interface/stlink.cfg",
        ]
        if openocd_target:
            server_args.extend([
                "-f",
                openocd_target if (
                    openocd_target.startswith("$") or "/" in openocd_target
                    or "\\" in openocd_target)
                else "target/%s" % openocd_target,
            ])
        server_args.extend([
            "-c",
            "transport select hla_swd; set WORKAREASIZE 0x4000",
        ])
        debug_tools["stlink"] = {
            "server": {
                "package": "tool-openocd",
                "executable": "bin/openocd",
                "arguments": server_args,
            },
            "onboard": "stlink" in debug.get("onboard_tools", []),
            "default": "stlink" in debug.get("default_tools", []),
        }
        return board

    def configure_debug_session(self, platform, debug_config):
        if debug_config.speed:
            server = debug_config.server or {}
            if "openocd" in server.get("executable", "").lower():
                server["arguments"].extend(
                    ["-c", "adapter speed %s" % debug_config.speed])

    # -- builder side ----------------------------------------------------

    def build_script(self, platform, board):
        # Local-keep family: the board-level skeleton is our own
        # stm32_build.py (no upstream platform to load from).
        return join(self.host_dir(), "builder", "families", "stm32",
                    "stm32_build.py")

    def framework_script(self, platform, framework, board):
        return None  # no Arduino support

    def zephyr_pioplatform(self):
        return "ststm32"
