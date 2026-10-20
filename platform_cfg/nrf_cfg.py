import sys

from platform_cfg.base import FamilyConfig

IS_WINDOWS = sys.platform.startswith("win")


class NrfConfig(FamilyConfig):
    family = "nrf"

    def configure_default_packages(self, variables, targets):
        upload_protocol = ""
        board = variables.get("board")
        frameworks = variables.get("pioframework", [])

        if board:
            upload_protocol = variables.get(
                "upload_protocol",
                self.board_config(board).get("upload.protocol", ""))

            self.mark_required("toolchain-gccarmnoneeabi")
            # Arduino BSP selection for nRF52840 boards comes from the manifest's
            # build.bsp.name ("adafruit" or "mbed"), not the board id substring.
            # Only nRF52840-family Arduino boards declare a BSP; nRF54 boards are
            # zephyr-only and never reach here.
            if "arduino" in frameworks:
                board_config = self.board_config(board)
                if (board_config.get("build.mcu", "") or "").startswith("nrf52"):
                    bsp = board_config.get("build.bsp.name", "")
                    if bsp not in ("adafruit", "mbed"):
                        sys.stderr.write(
                            "Error: board '%s' builds Arduino on an nRF52 MCU but "
                            "boards/%s.json has no valid build.bsp.name (expected "
                            "\"adafruit\" or \"mbed\").\n" % (board, board))
                        sys.exit(1)
                    if bsp == "adafruit":
                        self.platform.frameworks["arduino"]["package"] = "framework-arduinoadafruitnrf52"
                        self.mark_required("framework-cmsis", "tool-adafruit-nrfutil")
                    else:  # mbed
                        self.pin_version("toolchain-gccarmnoneeabi", "~1.80201.0")
                        self.mark_required("tool-openocd", "tool-bossac-nordicnrf52")
                        self.platform.frameworks["arduino"]["package"] = "framework-arduino-mbed"
                        # needed to build the ZIP file
                        self.mark_required("tool-adafruit-nrfutil")
                        self.platform.frameworks["arduino"][
                            "script"] = "builder/board_build/nrf/arduino-core-mbed.py"

            if "zephyr" in frameworks:
                self.mark_required("tool-cmake", "tool-dtc", "tool-ninja")
                self.pin_version("toolchain-gccarmnoneeabi", "~1.80201.0")
                if not IS_WINDOWS:
                    self.mark_required("tool-gperf")

        if set(["bootloader", "erase"]) & set(targets):
            self.mark_required("tool-nrfjprog")
        elif (upload_protocol and upload_protocol != "nrfjprog"):
            self.drop_package("tool-nrfjprog")

        self.prune_jlink(variables)

    def add_default_debug_tools(self, board):
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
                # Keep custom cfg paths unchanged; only prepend target/ for built-in script names.
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
