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

"""Atmel/Microchip SAM chip family (SAMD21 XIAO).

Owns the package matrix and the default debug-tools table, inlined from
the retired platform_cfg/samd_cfg.py (in the PR-122 form: the uploader
pruning loop is gone — it deleted other families' uploader packages
from the shared dict), plus the upstream builder lock: the board-level
skeleton is the official platform-atmelsam v9.0.0 builder/main.py,
executed by builder/families/samd/build.py, which re-applies the bossac
upload hardening (7b3b9e5) around it.

Package notes: framework-arduino-samd-seeed ~1.8.5 is the official
registry package (repository = Seeed-Studio/ArduinoCore-samd) — same
pin as upstream atmelsam, no rewrite. tool-bossac stays on our
~1.10901.0 pin (flag-compatible with upstream's sam-ba usage, tested);
framework-cmsis is pinned to ~2.50400.0 at configure time.
"""

import sys
from os.path import join

from .base import ChipFamily

IS_WINDOWS = sys.platform.startswith("win")


class SamdFamily(ChipFamily):
    family_ids = ("samd",)

    upstream_platform = "atmelsam"
    upstream_version = (
        "https://github.com/platformio/platform-atmelsam.git"
        "#6804c4b2f493e5f7df569462861622d70c2cdbd0"  # v9.0.0
    )

    owned_packages = ()

    # -- package matrix --------------------------------------------------

    def configure_default_packages(self, platform, variables, targets):
        if not variables.get("board"):
            return
        platform.packages["framework-arduino-samd-seeed"]["optional"] = False
        platform.packages["toolchain-gccarmnoneeabi"]["optional"] = False
        platform.packages["tool-bossac"]["optional"] = False
        platform.packages["framework-cmsis-atmel"]["optional"] = False

        platform.packages["framework-cmsis"]["optional"] = False
        platform.packages["framework-cmsis"]["version"] = "~2.50400.0"

        # Note: no uploader pruning here. The retired samd_cfg collected
        # every type == "uploader" package except the selected one and
        # deleted the rest, but samd's own uploaders (tool-bossac /
        # tool-jlink) carry no type field, so it deleted esp/renesas/nrf
        # uploaders from the shared packages dict too. Those packages
        # are optional and never install for samd builds (would-install
        # set verified identical without the loop), so deletion bought
        # nothing while breaking later in-process configuration of
        # those families (PR-122).

        # Every samd build runs the upstream builder skeleton; make
        # sure the locked checkout is present.
        self._ensure_upstream_platform(platform)

    # -- debug -----------------------------------------------------------

    def add_default_debug_tools(self, platform, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get("protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        # Atmel Ice / J-Link / BlackMagic Probe
        tools = ("blackmagic", "jlink", "atmel-ice", "cmsis-dap", "stlink")
        for link in tools:
            if link not in upload_protocols or link in debug["tools"]:
                continue
            if link == "blackmagic":
                debug["tools"]["blackmagic"] = {
                    "hwids": [["0x1d50", "0x6018"]],
                    "require_debug_port": True,
                }

            elif link == "jlink":
                assert debug.get("jlink_device"), (
                    "Missed J-Link Device ID for %s" % board.id
                )
                debug["tools"][link] = {
                    "server": {
                        "package": "tool-jlink",
                        "arguments": [
                            "-singlerun",
                            "-if",
                            "SWD",
                            "-select",
                            "USB",
                            "-device",
                            debug.get("jlink_device"),
                            "-port",
                            "2331",
                        ],
                        "executable": (
                            "JLinkGDBServerCL.exe"
                            if IS_WINDOWS
                            else "JLinkGDBServer"
                        ),
                    },
                    "onboard": link in debug.get("onboard_tools", []),
                }

            else:
                openocd_chipname = debug.get("openocd_chipname")
                assert openocd_chipname
                openocd_cmds = ["set CHIPNAME %s" % openocd_chipname]
                if link == "stlink" and "at91sam3" in openocd_chipname:
                    openocd_cmds.append("set CPUTAPID 0x2ba01477")
                server_args = [
                    "-s",
                    "$PACKAGE_DIR/openocd/scripts",
                    "-f",
                    "interface/%s.cfg" % (
                        "cmsis-dap" if link == "atmel-ice" else link),
                    "-c",
                    "; ".join(openocd_cmds),
                    "-f",
                    "target/%s.cfg" % debug.get("openocd_target"),
                ]
                debug["tools"][link] = {
                    "server": {
                        "package": "tool-openocd",
                        "executable": "bin/openocd",
                        "arguments": server_args,
                    },
                    "onboard": link in debug.get("onboard_tools", []),
                }
                if link == "stlink":
                    debug["tools"][link]["load_cmd"] = "preload"

        board.manifest["debug"] = debug
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
        return join(self.host_dir(), "builder", "families", "samd", "build.py")

    def framework_script(self, platform, framework, board):
        # The upstream arduino.py dispatches on build.system to
        # arduino/arduino-samd.py (which imports its sibling
        # arduino_common) — the retired local samd_arduino.py was the
        # semantically identical flattened copy of that chain.
        if framework != "arduino":
            return None
        return join(self._upstream_platform_dir(),
                    "builder", "frameworks", "arduino.py")
