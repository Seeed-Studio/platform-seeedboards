import sys

IS_WINDOWS = sys.platform.startswith("win")

# Black Magic Probe native USB VID:PID
BLACKMAGIC_PROBE_HWIDS = [["0x1d50", "0x6018"]]
# Default TCP port of the J-Link GDB server
JLINK_GDB_PORT = "2331"


def configure_samd_default_packages(self, variables, targets):
    board = self.board_config(variables.get("board"))
    upload_protocol = variables.get(
        "upload_protocol", board.get("upload.protocol", "")
    )
    disabled_pkgs = []
    upload_tool = "tool-openocd"
    if upload_protocol == "sam-ba":
        upload_tool = "tool-bossac"
    elif upload_protocol == "jlink":
        upload_tool = "tool-jlink"

    if upload_tool:
        for name, opts in self.packages.items():
            if "type" not in opts or opts["type"] != "uploader":
                continue
            if name != upload_tool:
                disabled_pkgs.append(name)


    self.packages["framework-arduino-samd-seeed"]["optional"] = False
    self.packages["toolchain-gccarmnoneeabi"]["optional"] = False
    self.packages["tool-bossac"]["optional"] = False
    self.packages["framework-cmsis-atmel"]["optional"] = False

    self.packages["framework-cmsis"]["optional"] = False
    self.packages["framework-cmsis"]["version"] = "~2.50400.0"

    for name in disabled_pkgs:
        # OpenOCD should be available when debugging
        if name == "tool-openocd" and variables.get("build_type", "") == "debug":
            continue
        del self.packages[name]



def _add_samd_default_debug_tools(self, board):
    debug = board.manifest.get("debug", {})
    upload_protocols = board.manifest.get("upload", {}).get("protocols", [])
    if "tools" not in debug:
        debug["tools"] = {}

    # Black Magic Probe / J-Link / Atmel ICE / CMSIS-DAP / ST-Link
    tools = ("blackmagic", "jlink", "atmel-ice", "cmsis-dap", "stlink")
    for link in tools:
        if link not in upload_protocols or link in debug["tools"]:
            continue
        if link == "blackmagic":
            debug["tools"]["blackmagic"] = {
                "hwids": BLACKMAGIC_PROBE_HWIDS,
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
                        JLINK_GDB_PORT,
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
            assert openocd_chipname, (
                "Missing debug.openocd_chipname for %s" % board.id
            )
            openocd_cmds = ["set CHIPNAME %s" % openocd_chipname]
            if link == "stlink" and "at91sam3" in openocd_chipname:
                # 0x2ba01477 is the standard ARM Cortex-M3 SW-DP ID (SAM3 boards)
                openocd_cmds.append("set CPUTAPID 0x2ba01477")
            server_args = [
                "-s",
                "$PACKAGE_DIR/openocd/scripts",
                "-f",
                "interface/%s.cfg" % ("cmsis-dap" if link == "atmel-ice" else link),
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



def configure_samd_debug_session(self, debug_config):
    if debug_config.speed:
        server_executable = (debug_config.server or {}).get("executable", "").lower()
        if "openocd" in server_executable:
            debug_config.server["arguments"].extend(
                ["-c", "adapter speed %s" % debug_config.speed]
            )
        elif "jlink" in server_executable:
            debug_config.server["arguments"].extend(
                ["-speed", debug_config.speed]
            )
