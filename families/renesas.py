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

"""Renesas RA chip family (RA4M1 XIAO).

Owns the package matrix and the default debug-tools table, inlined from
the retired platform_cfg/renesas_cfg.py, plus the upstream builder
lock: the board-level skeleton is the official platform-renesas-ra
v1.9.0 builder/main.py, executed by builder/families/renesas/build.py,
which re-applies the family upload deltas (pyocd hex graft, bossac
hardening) around it.

Package notes: framework-arduinorenesas-uno is the Seeed tarball
(1.2.2, variants trimmed to XIAORA4M1) served under the upstream
package name, so the upstream arduino.py's get_package_dir resolves it
directly (same mechanism as the nordic adafruit BSP). The board is not
upstream (boards/ has uno_r4/portenta_c33 only) — our board json stays
local, which does not affect the builder lock. Tool package specs have
zero drift against upstream v1.9.0.
"""

import sys
from os.path import join

from .base import ChipFamily

IS_WINDOWS = sys.platform.startswith("win")


class RenesasFamily(ChipFamily):
    family_ids = ("renesas",)

    # v1.9.0. The migration guide named the tag object 34112f8; the pin
    # is the commit it points at because _upstream_matches_lock's
    # rev-parse fallback compares HEAD against this SHA.
    upstream_platform = "renesas-ra"
    upstream_version = (
        "https://github.com/platformio/platform-renesas-ra.git"
        "#14e62388e2a4b195cc6ef83cbab4b1af95956ffb"  # v1.9.0 (tag 34112f8)
    )

    owned_packages = ("tool-dfuutil-arduino", "tool-bossac")

    # -- package matrix --------------------------------------------------

    def configure_default_packages(self, platform, variables, targets):
        if not variables.get("board"):
            return

        def _configure_uploader_packages(package_name, interface_name):
            use_conditions = [
                interface_name in variables.get(option, "")
                for option in ("upload_protocol", "debug_tool")
            ]
            if variables.get("board"):
                board_config = platform.board_config(variables.get("board"))
                use_conditions.extend(
                    [
                        interface_name in board_config.get(key, "")
                        for key in ("debug.default_tools", "upload.protocol")
                    ]
                )
            if not any(use_conditions) and package_name in platform.packages:
                self.drop_package(platform, package_name)
            else:
                platform.packages[package_name]["optional"] = False

        platform.packages["toolchain-gccarmnoneeabi"]["optional"] = False
        platform.packages["framework-arduinorenesas-uno"]["optional"] = False

        for package, interface in (
            ("tool-dfuutil-arduino", "dfu"),
            ("tool-bossac", "sam-ba"),
        ):
            _configure_uploader_packages(package, interface)

        # Every renesas build runs the upstream builder skeleton; make
        # sure the locked checkout is present.
        self._ensure_upstream_platform(platform)

    # -- debug -----------------------------------------------------------

    def add_default_debug_tools(self, platform, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get("protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        for link in ("jlink", "cmsis-dap"):
            if link not in upload_protocols or link in debug["tools"]:
                continue

            if link == "jlink":
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
                        "executable": ("JLinkGDBServerCL.exe"
                                       if IS_WINDOWS else
                                       "JLinkGDBServer")
                    },
                    "onboard": link in debug.get("onboard_tools", []),
                }
            elif link == "cmsis-dap" and board.id in (
                    "uno_r4_wifi", "uno_r4_minima", "seeed-xiao-ra4m1"):
                # Now OpenOCD does not have the ra4m1.cfg configuration file
                # so we provide it in this repository.
                server_args = [
                    "-s",
                    # Note: only `uno_r4_wifi` variant folder contains an
                    # OpenOCD script
                    join(platform.get_package_dir(
                        "framework-arduinorenesas-uno") or "",
                        "variants", "UNOWIFIR4"),
                    "-s",
                    "$PACKAGE_DIR/openocd/scripts",
                    "-f",
                    "interface/cmsis-dap.cfg",
                    "-f",
                    "%s/builder/families/renesas/ra4m1.cfg"
                    % self.host_dir(),
                    "-c",
                    "cmsis_dap_vid_pid %s %s" % ("0x0D28", "0x0204")
                ]

                debug["tools"][link] = {
                    "server": {
                        "package": "tool-openocd",
                        "executable": "bin/openocd",
                        "arguments": server_args,
                    },
                    # Derived from https://github.com/maxgerhardt/platform-renesas/blob/main/platform.py
                    # OpenOCD has no native flashing capabilities
                    # For the Renesas chips. We need to preload using the
                    # regular upload commands.
                    "load_cmds": "preload",
                    "init_cmds": [
                        "define pio_reset_halt_target",
                        "   monitor reset halt",
                        "end",
                        "define pio_reset_run_target",
                        "   monitor reset",
                        "end",
                        # make peripheral memory etc. readable
                        # since OpenOCD doesn't provide us with any target information (no flash driver etc.)
                        "set mem inaccessible-by-default off",
                        # fix to use hardware breakpoints of ARM CPU, not flash breakpoints. Doesn't break otherwise.
                        "mem 0 0x40000 ro",
                        "target extended-remote $DEBUG_PORT",
                        "$LOAD_CMDS",
                        "pio_reset_halt_target",
                        "$INIT_BREAK",
                    ],
                }

            # Only decorate tools this loop actually created: the cmsis-dap
            # branch is gated on a board-id whitelist, so a board listing
            # cmsis-dap without a branch would otherwise KeyError here.
            if link in debug["tools"]:
                debug["tools"][link]["onboard"] = link in debug.get(
                    "onboard_tools", []
                )
                debug["tools"][link]["default"] = link in debug.get(
                    "default_tools", []
                )

        board.manifest["debug"] = debug
        return board

    def configure_debug_session(self, platform, debug_config):
        adapter_speed = debug_config.speed or "5000"
        server_options = debug_config.server or {}
        server_arguments = server_options.get("arguments", [])
        if "jlink" in server_options.get("executable", "").lower():
            server_arguments.extend(["-speed", adapter_speed])

    # -- builder side ----------------------------------------------------

    def build_script(self, platform, board):
        # host_dir(), not platform.get_dir(): resolving inside the
        # wrapped window would point at the upstream package.
        return join(self.host_dir(), "builder", "families", "renesas", "build.py")

    def framework_script(self, platform, framework, board):
        # The upstream arduino.py resolves FRAMEWORK_DIR through
        # get_package_dir("framework-arduinorenesas-uno") — the Seeed
        # tarball under the upstream name; the retired local
        # renesas_arduino.py was its uno-only flattened copy (minus the
        # portenta_c33 branch and a stray debug print).
        if framework != "arduino":
            return None
        return join(self._upstream_platform_dir(),
                    "builder", "frameworks", "arduino.py")
