import sys

from platform_cfg.base import FamilyConfig

IS_WINDOWS = sys.platform.startswith("win")


class Stm32Config(FamilyConfig):
    family = "stm32"

    def configure_default_packages(self, variables, targets):
        board = variables.get("board")
        frameworks = variables.get("pioframework", [])

        if board:
            self.platform.packages["toolchain-gccarmnoneeabi"]["optional"] = False

            if "zephyr" in frameworks:
                for package_name in ("tool-cmake", "tool-dtc", "tool-ninja"):
                    self.platform.packages[package_name]["optional"] = False
                self.platform.packages["toolchain-gccarmnoneeabi"]["version"] = "~1.80201.0"
                if not IS_WINDOWS:
                    self.platform.packages["tool-gperf"]["optional"] = False

        jlink_requested = any(
            "jlink" in variables.get(option, "")
            for option in ("upload_protocol", "debug_tool")
        )
        if board:
            board_config = self.platform.board_config(board)
            jlink_requested = jlink_requested or any(
                "jlink" in board_config.get(key, "")
                for key in ("debug.default_tools", "upload.protocol")
            )
        if not jlink_requested and "tool-jlink" in self.platform.packages:
            del self.platform.packages["tool-jlink"]

    def add_default_debug_tools(self, board):
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
                openocd_target if (openocd_target.startswith("$") or "/" in openocd_target or "\\" in openocd_target)
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

    def configure_debug_session(self, debug_config):
        if debug_config.speed:
            server = debug_config.server or {}
            if "openocd" in server.get("executable", "").lower():
                server["arguments"].extend(["-c", "adapter speed %s" % debug_config.speed])
