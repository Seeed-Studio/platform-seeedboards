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

"""Nordic nRF chip family (nRF52 Arduino BSPs + nRF54 Zephyr/NCS).

Owns the package matrix, the default debug-tools table and the debug
session tweaks (inlined from the retired platform_cfg/nrf_cfg.py — the
per-family product-decision layer now lives with its family), plus the
upstream builder lock: the board-level skeleton is the official
platform-nordicnrf52 builder/main.py, executed by builder/families/
nordic/build.py with the upload deltas from upload.py around it.

Layout (D3' execution domains): this module is the Core-process family
class; everything the SCons process executes — the build wrapper, the
upload layer, the arduino hooks and fork, mcumgrupload.py and the
nRF54 OpenOCD configs — lives in builder/families/nordic/.
"""

import sys
from os.path import join

from .base import ChipFamily

IS_WINDOWS = sys.platform.startswith("win")


class NordicFamily(ChipFamily):
    family_ids = ("nrf",)
    owned_packages = ("tool-nrfjprog", "tool-jlink")

    upstream_platform = "nordicnrf52"
    upstream_version = (
        "https://github.com/platformio/platform-nordicnrf52.git"
        "#2df21c1424059ad549d13a30d79870103b4dbb68"  # v11.0.0
    )

    # -- package matrix --------------------------------------------------

    def configure_default_packages(self, platform, variables, targets):
        upload_protocol = ""
        board = variables.get("board")
        frameworks = variables.get("pioframework", [])

        if board:
            upload_protocol = variables.get(
                "upload_protocol",
                platform.board_config(board).get("upload.protocol", ""))

            platform.packages["toolchain-gccarmnoneeabi"]["optional"] = False
            # Arduino BSP selection for nRF52840 boards comes from the
            # manifest's build.bsp.name ("adafruit" or "mbed"), not the
            # board id substring. Only nRF52840-family Arduino boards
            # declare a BSP; nRF54 boards are zephyr-only and never get
            # here.
            if "arduino" in frameworks:
                board_config = platform.board_config(board)
                if (board_config.get("build.mcu", "") or "").startswith("nrf52"):
                    bsp = board_config.get("build.bsp.name", "")
                    if bsp not in ("adafruit", "mbed"):
                        sys.stderr.write(
                            "Error: board '%s' builds Arduino on an nRF52 MCU "
                            "but boards/%s.json has no valid build.bsp.name "
                            "(expected \"adafruit\" or \"mbed\").\n"
                            % (board, board))
                        sys.exit(1)
                    if bsp == "adafruit":
                        platform.frameworks["arduino"][
                            "package"] = "framework-arduinoadafruitnrf52"
                        platform.packages["framework-cmsis"]["optional"] = False
                        platform.packages["tool-adafruit-nrfutil"]["optional"] = False
                    else:  # mbed
                        platform.packages["toolchain-gccarmnoneeabi"][
                            "version"] = "~1.80201.0"
                        platform.packages["tool-openocd"]["optional"] = False
                        platform.packages["tool-bossac-nordicnrf52"]["optional"] = False
                        platform.frameworks["arduino"][
                            "package"] = "framework-arduino-mbed"
                        # needed to build the ZIP file
                        platform.packages["tool-adafruit-nrfutil"]["optional"] = False
                        # family-owned fork of the upstream mbed-core
                        # script (builder/families/nordic/ documents
                        # why it is not upstream yet)
                        platform.frameworks["arduino"][
                            "script"] = "builder/families/nordic/arduino-core-mbed.py"

            if "zephyr" in frameworks:
                for p in platform.packages:
                    if p in ("tool-cmake", "tool-dtc", "tool-ninja"):
                        platform.packages[p]["optional"] = False
                # framework-zephyr 4.4: the controller's hal/debug.h uses
                # the asm "inline" qualifier, which GCC < 9 rejects; 12.3
                # is what upstream nordicnrf52 pins for Zephyr.
                platform.packages["toolchain-gccarmnoneeabi"][
                    "version"] = "~1.120301.0"
                if not IS_WINDOWS:
                    platform.packages["tool-gperf"]["optional"] = False

        if set(["bootloader", "erase"]) & set(targets):
            platform.packages["tool-nrfjprog"]["optional"] = False
        elif (upload_protocol and upload_protocol != "nrfjprog"
                and "tool-nrfjprog" in platform.packages):
            del platform.packages["tool-nrfjprog"]

        # configure J-LINK tool
        jlink_conds = [
            "jlink" in variables.get(option, "")
            for option in ("upload_protocol", "debug_tool")
        ]
        if board:
            board_config = platform.board_config(board)
            jlink_conds.extend([
                "jlink" in board_config.get(key, "")
                for key in ("debug.default_tools", "upload.protocol")
            ])
        if not any(jlink_conds):
            self.drop_package(platform, "tool-jlink")

        # Every nrf build (arduino, zephyr, bare) runs the upstream
        # builder skeleton; make sure the locked checkout is present.
        self._ensure_upstream_platform(platform)

    # -- debug -----------------------------------------------------------

    def add_default_debug_tools(self, platform, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get(
            "protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        # J-Link / ST-Link / BlackMagic Probe
        for link in ("blackmagic", "jlink", "stlink", "cmsis-dap"):
            if link not in upload_protocols or link in debug['tools']:
                continue

            if link == "blackmagic":
                debug["tools"]["blackmagic"] = {
                    "hwids": [["0x1d50", "0x6018"]],
                    "require_debug_port": True
                }

            elif link == "jlink":
                assert debug.get("jlink_device"), (
                    "Missed J-Link Device ID for %s" % board.id)
                debug["tools"][link] = {
                    "server": {
                        "package": "tool-jlink",
                        "arguments": [
                            "-singlerun",
                            "-if", "SWD",
                            "-select", "USB",
                            "-device", debug.get("jlink_device"),
                            "-port", "2331"
                        ],
                        "executable": ("JLinkGDBServerCL.exe"
                                       if IS_WINDOWS else
                                       "JLinkGDBServer")
                    }
                }

            else:
                openocd_target = debug.get("openocd_target")
                assert openocd_target, ("Missing target configuration for %s" %
                                        board.id)
                server_args = [
                    "-s", "$PACKAGE_DIR/openocd/scripts",
                    "-f", "interface/%s.cfg" % link
                ]
                # Keep custom cfg paths unchanged; only prepend target/
                # for built-in script names.
                if openocd_target.startswith("$") or "/" in openocd_target or "\\" in openocd_target:
                    server_args.append("-f")
                    server_args.append(openocd_target)
                else:
                    server_args.append("-f")
                    server_args.append("target/%s" % openocd_target)

                if link == "stlink":
                    server_args.extend([
                        "-c",
                        "transport select hla_swd; set WORKAREASIZE 0x4000"
                    ])
                debug["tools"][link] = {
                    "server": {
                        "package": "tool-openocd",
                        "executable": "bin/openocd",
                        "arguments": server_args
                    }
                }
                server_args.extend(debug.get("openocd_extra_args", []))

            debug["tools"][link]["onboard"] = link in debug.get("onboard_tools", [])
            debug["tools"][link]["default"] = link in debug.get("default_tools", [])

        board.manifest['debug'] = debug
        return board

    def configure_debug_session(self, platform, debug_config):
        if debug_config.speed:
            server_executable = (debug_config.server or {}).get(
                "executable", "").lower()
            if "openocd" in server_executable:
                debug_config.server["arguments"].extend(
                    ["-c", "adapter speed %s" % debug_config.speed]
                )
            elif "jlink" in server_executable:
                debug_config.server["arguments"].extend(
                    ["-speed", debug_config.speed]
                )

    # -- builder side ----------------------------------------------------

    def build_script(self, platform, board):
        # host_dir(), not platform.get_dir(): resolving inside the
        # wrapped window would point at the upstream package.
        return join(self.host_dir(), "builder", "families", "nordic", "build.py")

    def framework_script(self, platform, framework, board):
        # mbed-BSP boards never reach the dispatcher hook path: their
        # framework script is repointed at configure time (see the
        # package matrix above). Adafruit-BSP boards load the upstream
        # adafruit.py plus the hooks below; nRF54 boards are
        # zephyr-only and declare no build.bsp.name.
        if framework != "arduino":
            return None
        if board.get("build.bsp.name", "") != "adafruit":
            return None
        return join(self._upstream_platform_dir(),
                    "builder", "frameworks", "arduino", "adafruit.py")

    def get_build_hooks(self, framework):
        if framework != "arduino":
            return []
        # builder/ is not a package: the hooks module comes into reach
        # the same way builder/frameworks/zephyr.py reaches zephyr_fixes
        # — its directory on sys.path.
        hooks_dir = join(self.host_dir(), "builder", "families", "nordic")
        if hooks_dir not in sys.path:
            sys.path.insert(0, hooks_dir)
        import arduino_hooks
        return [arduino_hooks.bsp_libraries_on_libpath,
                arduino_hooks.keep_local_wrap_set]

    def zephyr_pioplatform(self):
        return "nordicnrf52"
