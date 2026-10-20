import sys

from platform_cfg.base import FamilyConfig

IS_WINDOWS = sys.platform.startswith("win")


class SamdConfig(FamilyConfig):
    family = "samd"

    def configure_default_packages(self, variables, targets):
        if not variables.get("board"):
            # The original module-level hook called bare super() here, which
            # cannot resolve outside a class; the branch is unreachable in
            # practice (PlatformIO always supplies a board) and platform.py
            # discards the hook's return value -- so simply defer nothing.
            return
        board = self.platform.board_config(variables.get("board"))
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
            for name, opts in self.platform.packages.items():
                if "type" not in opts or opts["type"] != "uploader":
                    continue
                if name != upload_tool:
                    disabled_pkgs.append(name)


        self.mark_required(
            "framework-arduino-samd-seeed",
            "toolchain-gccarmnoneeabi",
            "tool-bossac",
            "framework-cmsis-atmel",
            "framework-cmsis",
        )
        self.pin_version("framework-cmsis", "~2.50400.0")

        print("optional is:",self.platform.packages["framework-cmsis"]["optional"])
        print("optional is:",self.platform.packages["framework-cmsis"]["version"])

        for name in disabled_pkgs:
            # OpenOCD should be available when debugging
            if name == "tool-openocd" and variables.get("build_type", "") == "debug":
                continue
            del self.platform.packages[name]

    def add_default_debug_tools(self, board):
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

    def configure_debug_session(self, debug_config):
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
