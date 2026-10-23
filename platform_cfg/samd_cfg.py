import sys
IS_WINDOWS = sys.platform.startswith("win")


def configure_samd_default_packages(self, variables, targets):
    if not variables.get("board"):
        return super().configure_default_packages(variables, targets)
    board = self.board_config(variables.get("board"))

    # Uploader pruning removed: the old code collected every type=uploader
    # package except the one selected for this board and deleted the rest,
    # but samd's own uploaders (tool-bossac / tool-jlink) carry no type
    # field, so it deleted esp/renesas/nrf uploaders from the shared
    # self.packages dict too. Those packages are optional and never
    # install for samd builds (would-install set verified identical
    # without the loop), so deletion bought nothing while breaking later
    # in-process configuration of those families.

    self.packages["framework-arduino-samd-seeed"]["optional"] = False
    self.packages["toolchain-gccarmnoneeabi"]["optional"] = False
    self.packages["tool-bossac"]["optional"] = False
    self.packages["framework-cmsis-atmel"]["optional"] = False

    self.packages["framework-cmsis"]["optional"] = False
    self.packages["framework-cmsis"]["version"] = "~2.50400.0"



def _add_samd_default_debug_tools(self, board):
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