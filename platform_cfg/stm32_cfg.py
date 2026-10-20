import sys

from platform_cfg.base import FamilyConfig

IS_WINDOWS = sys.platform.startswith("win")


class Stm32Config(FamilyConfig):
    family = "stm32"

    def configure_default_packages(self, variables, targets):
        board = variables.get("board")
        frameworks = variables.get("pioframework", [])

        if board:
            self.mark_required("toolchain-gccarmnoneeabi")

            if "zephyr" in frameworks:
                self.mark_required("tool-cmake", "tool-dtc", "tool-ninja")
                self.pin_version("toolchain-gccarmnoneeabi", "~1.80201.0")
                if not IS_WINDOWS:
                    self.mark_required("tool-gperf")

        self.prune_jlink(variables)

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
