"""Renesas RA family (RA4M1) — Arduino core.

Adapted from the predecessor repo (upstream: ArduinoCore-renesas-uno /
platform-renesas). OpenOCD has no native ra4m1 target config, so the
platform ships one (builder/board_build/renesas/ra4m1.cfg) and the
cmsis-dap debug tool preloads instead of flashing -- both inherited
from maxgerhardt/platform-renesas.
"""

import os
import sys
from os.path import dirname, join

from families.base import ChipFamily

_SCRIPTS_DIR = dirname(__file__)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

IS_WINDOWS = sys.platform.startswith("win")

# DAPLink debug adapter USB VID/PID for OpenOCD's cmsis_dap_vid_pid command
DAPLINK_VID = "0x0D28"
DAPLINK_PID = "0x0204"
# Fallback J-Link adapter speed (kHz) when no debug speed is configured
DEFAULT_JLINK_SPEED_KHZ = "5000"


class RenesasFamily(ChipFamily):
    family_ids = ("renesas",)

    def required_packages(self, board, variables=None) -> "dict[str, object]":
        packages = {
            "framework-arduinorenesas-uno": None,
            # ArduinoCore-renesas-uno validates the GCC 7 line; leaving
            # the platform-wide range would silently move to GCC 12
            # (ADR-0002 records that exact predecessor regression).
            "toolchain-gccarmnoneeabi": "~1.70201.0",
        }
        # Uploaders stay optional unless the active protocol needs them
        # (project upload_protocol overrides the manifest default).
        protocol = (board.get("upload") or {}).get("protocol", "")
        if variables is not None:
            protocol = variables.get("upload_protocol") or protocol
        if protocol == "dfu":
            packages["tool-dfuutil-arduino"] = "~1.11.0"
        elif protocol == "sam-ba":
            packages["tool-bossac"] = "~1.10901.0"
        return packages

    def build_flags(self, board) -> list:
        return []

    def upload_protocol(self, board) -> str:
        return (board.get("upload") or {}).get("protocol", "dfu")

    def build_script(self, env, board) -> str:
        return join(dirname(_SCRIPTS_DIR), "builder", "board_build", "renesas",
                    "renesas_build.py")

    def arduino_script(self, env, board) -> str:
        return "../board_build/renesas/renesas_arduino.py"

    def inject_debug_tools(self, board) -> None:
        debug = board.manifest.setdefault("debug", {})
        if "tools" in debug:
            return
        debug.setdefault("tools", {})
        upload_protocols = (board.manifest.get("upload") or {}).get(
            "protocols", [])

        for link in ("jlink", "cmsis-dap"):
            if link not in upload_protocols or link in debug["tools"]:
                continue

            if link == "jlink":
                jlink_device = debug.get("jlink_device")
                assert jlink_device, (
                    "Missed J-Link Device ID for %s" % board.id)
                debug["tools"][link] = {
                    "server": {
                        "package": "tool-jlink",
                        "arguments": [
                            "-singlerun",
                            "-if", "SWD",
                            "-select", "USB",
                            "-device", jlink_device,
                            "-port", "2331",
                        ],
                        "executable": ("JLinkGDBServerCL.exe"
                                       if IS_WINDOWS else "JLinkGDBServer"),
                    },
                    "onboard": link in debug.get("onboard_tools", []),
                }
            elif board.id == "seeed-xiao-ra4m1":
                # OpenOCD has no ra4m1.cfg target config -- this platform
                # ships one. Inherited from
                # maxgerhardt/platform-renesas: OpenOCD cannot flash
                # Renesas chips, so the image is preloaded with the
                # regular upload commands instead.
                platform_dir = dirname(dirname(_SCRIPTS_DIR))
                framework_dir = self._framework_dir("framework-arduinorenesas-uno")
                server_args = [
                    "-s",
                    # only the UNOWIFIR4 variant folder carries an
                    # OpenOCD script dir
                    join(framework_dir or "", "variants", "UNOWIFIR4"),
                    "-s", "$PACKAGE_DIR/openocd/scripts",
                    "-f", "interface/cmsis-dap.cfg",
                    "-f", join(platform_dir, "builder", "board_build",
                               "renesas", "ra4m1.cfg"),
                    "-c", "cmsis_dap_vid_pid %s %s" % (DAPLINK_VID, DAPLINK_PID),
                ]

                debug["tools"][link] = {
                    "server": {
                        "package": "tool-openocd",
                        "executable": "bin/openocd",
                        "arguments": server_args,
                    },
                    "load_cmds": "preload",
                    "init_cmds": [
                        "define pio_reset_halt_target",
                        "   monitor reset halt",
                        "end",
                        "define pio_reset_run_target",
                        "   monitor reset",
                        "end",
                        # make peripheral memory readable: OpenOCD has no
                        # target information for this chip (no flash driver)
                        "set mem inaccessible-by-default off",
                        # hardware breakpoints of the ARM CPU, not flash
                        # breakpoints; breaks otherwise
                        "mem 0 0x40000 ro",  # 256 KB flash region
                        "target extended-remote $DEBUG_PORT",
                        "$LOAD_CMDS",
                        "pio_reset_halt_target",
                        "$INIT_BREAK",
                    ],
                }

            if link in debug["tools"]:
                debug["tools"][link]["onboard"] = (
                    link in debug.get("onboard_tools", []))
                debug["tools"][link]["default"] = (
                    link in debug.get("default_tools", []))

        board.manifest["debug"] = debug

    def configure_debug_session(self, debug_config) -> None:
        adapter_speed = debug_config.speed or DEFAULT_JLINK_SPEED_KHZ
        server_options = debug_config.server or {}
        server_arguments = server_options.get("arguments", [])
        if "jlink" in server_options.get("executable", "").lower():
            server_arguments.extend(["-speed", adapter_speed])

    @staticmethod
    def _framework_dir(name):
        """Best-effort framework package dir for server script paths."""
        try:
            from platformio.project.config import ProjectConfig
            config = ProjectConfig.get_instance()
            packages_dir = config.get("platformio", "packages_dir")
            path = os.path.join(packages_dir, name)
            return path if os.path.isdir(path) else None
        except Exception:  # pylint: disable=broad-except
            return None
