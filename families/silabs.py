"""Silicon Labs family (XIAO MG24 / MG24 Sense) — Arduino core.

Adapted from the predecessor repo. The Silicon Labs Arduino core needs
an OpenOCD build with EFR32 support, which the registry tool-openocd
does not carry: Seeed hosts per-OS builds. That is a slot collision
with the zephyr family's registry pin (~3.1200.0) under the ADR-0002
single-slot rule, so the package gets its own name --
tool-openocd-silabs -- instead of a per-family version override on the
shared slot (the predecessor did the override and documented the
multi-env breakage it caused).
"""

import sys
from os.path import dirname, join

from families.base import ChipFamily

_SCRIPTS_DIR = dirname(__file__)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Pinned GCC ARM toolchain line required by the Silicon Labs core
GCCARM_TOOLCHAIN_VERSION = "~1.120301.0"

# Seeed-hosted OpenOCD builds with EFR32 support, per host system.
SEEED_OPENOCD = {
    "darwin": "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-apple.tar.gz",
    "linux": "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-linux.tar.gz",
    "windows": "https://files.seeedstudio.com/arduino/platformio/forsilicon-openocd-win.zip",
}


class SilabsFamily(ChipFamily):
    family_ids = ("silabs",)

    def required_packages(self, board, variables=None) -> "dict[str, object]":
        # platformio is imported lazily (repo root on sys.path would
        # shadow the stdlib platform module at import time).
        from platformio import util

        sys_type = util.get_systype()
        openocd_url = None
        for prefix, url in SEEED_OPENOCD.items():
            if prefix in sys_type:
                openocd_url = url
                break
        if openocd_url is None:
            raise ValueError(
                "no Silicon Labs OpenOCD build for host system %r "
                "(families/silabs.py)" % sys_type
            )
        return {
            "framework-arduino-silabs": None,
            "toolchain-gccarmnoneeabi": GCCARM_TOOLCHAIN_VERSION,
            "tool-openocd-silabs": openocd_url,
        }

    def build_flags(self, board) -> list:
        return []

    def upload_protocol(self, board) -> str:
        return (board.get("upload") or {}).get("protocol", "cmsis-dap")

    def build_script(self, env, board) -> str:
        return join(dirname(_SCRIPTS_DIR), "builder", "board_build", "silabs",
                    "silabs_build.py")

    def arduino_script(self, env, board) -> str:
        return "../board_build/silabs/silabs_arduino.py"

    def inject_debug_tools(self, board) -> None:
        debug = board.manifest.setdefault("debug", {})
        if "tools" in debug:
            return

        openocd_target = debug.get("openocd_target")
        assert openocd_target, (
            "Missing target configuration for %s" % board.id)
        debug["tools"] = {
            "cmsis-dap": {
                "server": {
                    "executable": "bin/openocd",
                    "package": "tool-openocd-silabs",
                    "arguments": [
                        "-s", "$PACKAGE_DIR/share/openocd/scripts",
                        "-f", "interface/cmsis-dap.cfg",
                        "-f", "target/%s" % openocd_target,
                        "-c", "adapter speed 1000",
                    ],
                },
                "load_cmds": "preload",
                "init_cmds": [
                    "target extended-remote $DEBUG_PORT",
                    "$LOAD_CMDS",
                    "pio_reset_halt_target",
                    "$INIT_BREAK",
                ],
            }
        }
        board.manifest["debug"] = debug

    def configure_debug_session(self, debug_config) -> None:
        if debug_config.speed:
            if "jlink" in (debug_config.server or {}).get(
                    "executable", "").lower():
                debug_config.server["arguments"].extend(
                    ["-speed", debug_config.speed]
                )
