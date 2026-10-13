import os
import sys

IS_WINDOWS = sys.platform.startswith("win")

# DAPLink debug adapter USB VID/PID for OpenOCD's cmsis_dap_vid_pid command
DAPLINK_VID = "0x0D28"
DAPLINK_PID = "0x0204"
# Fallback J-Link adapter speed (kHz) when no debug speed is configured
DEFAULT_JLINK_SPEED_KHZ = "5000"


def configure_renesas_default_packages(self, variables, targets):
    def _configure_uploader_packages(package_name, interface_name):
        use_conditions = [
            interface_name in variables.get(option, "")
            for option in ("upload_protocol", "debug_tool")
        ]
        if variables.get("board"):
            board_config = self.board_config(variables.get("board"))
            use_conditions.extend(
                [
                    interface_name in board_config.get(key, "")
                    for key in ("debug.default_tools", "upload.protocol")
                ]
            )
        if not any(use_conditions) and package_name in self.packages:
            del self.packages[package_name]
        else:
            self.packages[package_name]["optional"] = False

    self.packages["toolchain-gccarmnoneeabi"]["optional"] = False
    self.packages["framework-arduinorenesas-uno"]["optional"] = False

    for package, interface in (
        ("tool-dfuutil-arduino", "dfu"),
        ("tool-bossac", "sam-ba"),
    ):
        _configure_uploader_packages(package, interface)



def _add_renesas_default_debug_tools(self, board):
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
        elif link == "cmsis-dap" and board.id in ("seeed-xiao-ra4m1",):

            # Now OpenOCD does not have the ra4m1.cfg configuration file
            # so we provide it in this repository.
            current_file_path = os.path.abspath(__file__)
            current_dir = os.path.dirname(current_file_path)
            parent_dir = os.path.dirname(current_dir)

            server_args = [
                "-s",
                # Note: only `uno_r4_wifi` variant folder contains an OpenOCD script
                os.path.join(
                    self.get_package_dir("framework-arduinorenesas-uno") or "",
                    "variants",
                    "UNOWIFIR4",
                ),
                "-s",
                "$PACKAGE_DIR/openocd/scripts",
                "-f",
                "interface/cmsis-dap.cfg",
                "-f",
                "%s/builder/board_build/renesas/ra4m1.cfg" % parent_dir,
                "-c",
                "cmsis_dap_vid_pid %s %s" % (DAPLINK_VID, DAPLINK_PID)
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
                    "mem 0 0x40000 ro",  # 256 KB flash region
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



def configure_renesas_debug_session(self, debug_config):
    adapter_speed = debug_config.speed or DEFAULT_JLINK_SPEED_KHZ
    server_options = debug_config.server or {}
    server_arguments = server_options.get("arguments", [])
    if "jlink" in server_options.get("executable", "").lower():
        server_arguments.extend(["-speed", adapter_speed])
