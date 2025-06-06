import sys
IS_WINDOWS = sys.platform.startswith("win")

def configure_nrf_default_packages(self, variables, targets):
    upload_protocol = ""
    board = variables.get("board")
    frameworks = variables.get("pioframework", [])
    
    if board:
        upload_protocol = variables.get(
            "upload_protocol",
            self.board_config(board).get("upload.protocol", ""))

        self.packages["toolchain-gccarmnoneeabi"]["optional"] = False
        # if board in ("seeed-xiao-afruitnrf52-nrf52840", "seeed-xiao-ble-nrf52840-sense"):
        if "arduino" in frameworks:
            self.frameworks["arduino"][
                "package"] = "framework-arduinoadafruitnrf52"
            self.packages["framework-cmsis"]["optional"] = False
            self.packages["tool-adafruit-nrfutil"]["optional"] = False

        if "mbed" in frameworks:
            # self.packages["toolchain-gccarmnoneeabi"]["optional"] = False
            self.packages["toolchain-gccarmnoneeabi"]["version"] = "~1.90201.0"
            # self.packages["tool-openocd"]["optional"] = False
            # self.packages["tool-bossac-nordicnrf52"]["optional"] = False
            # self.frameworks["arduino"]["package"] = "framework-arduino-mbed"
            #     # needed to build the ZIP file
            # self.packages["tool-adafruit-nrfutil"]["optional"] = False

            # self.frameworks["arduino"][
            #     "script"
            # ] = "builder/board_build/nrf/arduino-core-mbed.py"
            
        if "zephyr" in frameworks:
            for p in self.packages:
                if p in ("tool-cmake", "tool-dtc", "tool-ninja"):
                    self.packages[p]["optional"] = False
            self.packages["toolchain-gccarmnoneeabi"]["version"] = "~1.80201.0"
            if not IS_WINDOWS:
                self.packages["tool-gperf"]["optional"] = False

    if set(["bootloader", "erase"]) & set(targets):
        self.packages["tool-nrfjprog"]["optional"] = False
    elif (upload_protocol and upload_protocol != "nrfjprog"
            and "tool-nrfjprog" in self.packages):
        del self.packages["tool-nrfjprog"]

    # configure J-LINK tool
    jlink_conds = [
        "jlink" in variables.get(option, "")
        for option in ("upload_protocol", "debug_tool")
    ]
    if board:
        board_config = self.board_config(board)
        jlink_conds.extend([
            "jlink" in board_config.get(key, "")
            for key in ("debug.default_tools", "upload.protocol")
        ])
    jlink_pkgname = "tool-jlink"
    if not any(jlink_conds) and jlink_pkgname in self.packages:
        del self.packages[jlink_pkgname]


def _add_nrf_default_debug_tools(self, board):
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
                "-f", "interface/%s.cfg" % link,
                "-f", "%s" % openocd_target
            ]
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


def configure_nrf_debug_session(self, debug_config):
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
