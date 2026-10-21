"""Nordic nRF52 family (XIAO nRF52840 line) — two Arduino cores.

The 52840 boards ship on one of two Arduino cores, selected by the
manifest's build.core:

    nRF5     Adafruit nRF52 core (framework-arduinoadafruitnrf52 +
             framework-cmsis). Links only on the GCC 7 line: GCC 12
             fails with undefined USB CDC symbols (core 1.10x).
    arduino  ArduinoCore-mbed (framework-arduino-mbed, Seeed build),
             validated on the GCC 8 line.

Both pins live on the shared toolchain-gccarmnoneeabi slot -- the
per-env process isolation of the CI matrix (one `pio run -e` per env)
keeps them from fighting, the same decision the predecessor validated
(ADR-0002 single-slot rule: collision carried as evidence-commented
overrides).

The nRF54 Zephyr boards are NOT in this family -- they route to the
zephyr family via build.chip_family.
"""

import sys
from os.path import dirname, join

from families.base import ChipFamily

_SCRIPTS_DIR = dirname(__file__)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

IS_WINDOWS = sys.platform.startswith("win")


class NrfFamily(ChipFamily):
    family_ids = ("nrf",)

    def required_packages(self, board, variables=None) -> "dict[str, object]":
        build = board.get("build") or {}
        core = build.get("core")
        if core == "nRF5":
            return {
                "framework-arduinoadafruitnrf52": None,
                "framework-cmsis": "~2.50700.0",
                "tool-adafruit-nrfutil": "~1.503.0",
                # Adafruit nRF52 core (1.10x) links only on the GCC 7
                # line; GCC 12 fails with undefined USB CDC symbols.
                "toolchain-gccarmnoneeabi": "~1.70201.0",
            }
        if core == "arduino":
            return {
                "framework-arduino-mbed": None,
                "tool-adafruit-nrfutil": "~1.503.0",
                "tool-bossac-nordicnrf52": "~1.10901.0",
                "tool-openocd": "~3.1200.0",
                # ArduinoCore-mbed for nRF52840, validated on GCC 8.
                "toolchain-gccarmnoneeabi": "~1.80201.0",
            }
        raise ValueError(
            "unsupported build.core %r for the nrf family (expected "
            "'nRF5' or 'arduino'); see families/nrf.py" % core
        )

    def build_flags(self, board) -> list:
        return []

    def upload_protocol(self, board) -> str:
        return (board.get("upload") or {}).get("protocol", "nrfutil")

    def build_script(self, env, board) -> str:
        return join(dirname(_SCRIPTS_DIR), "builder", "board_build", "nrf",
                    "nrf_build.py")

    def arduino_script(self, env, board) -> str:
        core = (board.get("build") or {}).get("core")
        if core == "nRF5":
            return "../board_build/nrf/nrf_arduino.py"
        if core == "arduino":
            return "../board_build/nrf/arduino-core-mbed.py"
        raise RuntimeError(
            "unsupported build.core %r for the nrf family arduino entry"
            % core
        )

    def inject_debug_tools(self, board) -> None:
        debug = board.manifest.setdefault("debug", {})
        if "tools" in debug:
            return
        debug.setdefault("tools", {})
        upload_protocols = (board.manifest.get("upload") or {}).get(
            "protocols", [])

        for link in ("blackmagic", "jlink", "stlink", "cmsis-dap"):
            if link not in upload_protocols or link in debug["tools"]:
                continue

            if link == "blackmagic":
                debug["tools"]["blackmagic"] = {
                    "hwids": [["0x1d50", "0x6018"]],
                    "require_debug_port": True,
                }
            elif link == "jlink":
                jlink_device = debug.get("jlink_device")
                assert jlink_device, (
                    "Missing J-Link Device ID for %s" % board.id)
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
                    }
                }
            else:
                openocd_target = debug.get("openocd_target")
                assert openocd_target, (
                    "Missing target configuration for %s" % board.id)
                server_args = [
                    "-s", "$PACKAGE_DIR/openocd/scripts",
                    "-f", "interface/%s.cfg" % link,
                ]
                if (openocd_target.startswith("$") or "/" in openocd_target
                        or "\\" in openocd_target):
                    server_args.extend(["-f", openocd_target])
                else:
                    server_args.extend(["-f", "target/%s" % openocd_target])
                if link == "stlink":
                    server_args.extend([
                        "-c",
                        "transport select hla_swd; set WORKAREASIZE 0x4000",
                    ])
                debug["tools"][link] = {
                    "server": {
                        "package": "tool-openocd",
                        "executable": "bin/openocd",
                        "arguments": server_args,
                    }
                }
                server_args.extend(debug.get("openocd_extra_args", []))

            debug["tools"][link]["onboard"] = (
                link in debug.get("onboard_tools", []))
            debug["tools"][link]["default"] = (
                link in debug.get("default_tools", []))

        board.manifest["debug"] = debug

    def configure_debug_session(self, debug_config) -> None:
        if not debug_config.speed:
            return
        server_executable = (debug_config.server or {}).get(
            "executable", "").lower()
        if "openocd" in server_executable:
            debug_config.server["arguments"].extend(
                ["-c", "adapter speed %s" % debug_config.speed]
            )
        elif "jlink" in server_executable:
            debug_config.server["arguments"].extend(
                ["-speed", debug_config.speed]
            )
