"""Zephyr family — boards built with the Zephyr RTOS (ADR-0001, ADR-0003).

The family key is the build OS, not the silicon: nRF54L15/LM20 and
STM32C5 boards share one Zephyr flow. Everything silicon-specific
stays manifest-driven (zero-string routing):

    build.zephyr.package     framework-zephyr-* package for this board
    build.zephyr.board_name  tree under zephyr/boards/arm/<name>/
                             (custom board def + fixes/ directory,
                             ADR-0003 directory convention)
    build.zephyr.masquerade  upstream $PIOPLATFORM the west manifest /
                             bundled build script HAL selection expects
    build.zephyr.variant     -DBOARD= value for the cmake invocation

The framework script (builder/board_build/zephyr/zephyr_framework.py)
is adapted from the predecessor repo's proven Zephyr integration; the
fixes applier and executors below it are ported unchanged.
"""

import sys
from os.path import dirname, join

from families.base import ChipFamily

_SCRIPTS_DIR = dirname(__file__)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

IS_WINDOWS = sys.platform.startswith("win")

# Debug links the family can synthesize openocd/jlink servers for;
# gated on the manifest's upload.protocols (board facts, not literals).
DEBUG_LINKS = ("blackmagic", "jlink", "stlink", "cmsis-dap")


class ZephyrFamily(ChipFamily):
    family_ids = ("zephyr",)

    def required_packages(self, board, variables=None) -> "dict[str, object]":
        zephyr = (board.get("build") or {}).get("zephyr") or {}
        framework_package = zephyr.get("package")
        if not framework_package:
            raise ValueError(
                "board declares zephyr but no build.zephyr.package "
                "(families/zephyr.py required_packages)"
            )
        packages = {
            framework_package: None,
            # Zephyr 4.x builds use the GCC 12 line: GCC 14 removes the
            # CMSIS 6 intrinsics (__sxtb16 et al) -- validated broken by
            # the predecessor's zephyr matrix.
            "toolchain-gccarmnoneeabi": "~1.120301.0",
            "tool-cmake": "~3.30.2",
            "tool-dtc": "~1.4.7",
            "tool-ninja": "^1.7.0",
            "tool-scons": None,
            "tool-openocd": "~3.1200.0",
        }
        if not IS_WINDOWS:
            packages["tool-gperf"] = None
        return packages

    def build_flags(self, board) -> list:
        # Zephyr builds are cmake-driven; the framework package's build
        # script derives all flags from the board tree and prj.conf.
        return []

    def upload_protocol(self, board) -> str:
        return (board.get("upload") or {}).get("protocol", "cmsis-dap")

    def build_script(self, env, board) -> str:
        return join(dirname(_SCRIPTS_DIR), "builder", "board_build", "zephyr",
                    "zephyr_build.py")

    def zephyr_script(self, env, board) -> str:
        return "../board_build/zephyr/zephyr_framework.py"

    def inject_debug_tools(self, board) -> None:
        debug = board.manifest.setdefault("debug", {})
        if "tools" in debug:
            return
        debug.setdefault("tools", {})
        upload_protocols = (board.manifest.get("upload") or {}).get(
            "protocols", [])

        for link in DEBUG_LINKS:
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
                # Custom cfg paths (e.g. the platform's own nrf54 cfgs)
                # pass through unchanged; bare names resolve under
                # target/.
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
