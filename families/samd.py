"""SAMD family (SAMD21/SAMD51) — the first ChipFamily implementation.

Behavior sourced from upstream platformio/platform-atmelsam current
state and the predecessor's samd_cfg/board_build code. Debug-tool
injection follows the upstream PlatformBase pattern; package pins
follow ADR-0002 (registry cmsis, version narrowed where the seeed core
validates a specific line).
"""

import sys
from os.path import dirname, join

from families.base import ChipFamily

IS_WINDOWS = sys.platform.startswith("win")

# board_build/ carries the family's SCons scripts; the helpers module
# (predecessor's samd_cfg) stays next to them for import.
_SCRIPTS_DIR = dirname(__file__)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


class SamdFamily(ChipFamily):
    family_ids = ("samd", "same5")

    # ------------------------------------------------------------------
    # Package activation (called from platform.py)
    # ------------------------------------------------------------------

    def required_packages(self, board) -> "dict[str, object]":
        mcu = (board.get("build") or {}).get("mcu", "")
        packages = {
            "toolchain-gccarmnoneeabi": None,  # platform.json range
            "framework-arduino-samd-seeed": None,
            "framework-cmsis": "~2.50400.0",   # seeed core needs 2.5.x (ADR-0002)
            "framework-cmsis-atmel": None,
        }
        protocol = (board.get("upload") or {}).get("protocol", "")
        if protocol == "sam-ba":
            packages["tool-bossac"] = "~1.10901.0"
        return packages

    # ------------------------------------------------------------------
    # Build config (called from builder/main.py)
    # ------------------------------------------------------------------

    def build_flags(self, board) -> list:
        mcu = (board.get("build") or {}).get("mcu", "")
        flags = ["-DARDUINO_ARCH_SAMD"]
        if mcu.startswith("samd51") or mcu.startswith("same51"):
            flags.append("-D__SAMD51__")
        elif mcu.startswith("samd21"):
            flags.append("-D__SAMD21__")
        return flags

    def upload_protocol(self, board) -> str:
        protocol = (board.get("upload") or {}).get("protocol")
        return protocol if protocol else "sam-ba"

    def build_script(self, env, board) -> str:
        # The family build script is the full entry: it sets the ARM
        # toolchain env, registers upload actions, and dispatches the
        # framework script. Pointing at the framework entry directly
        # skips the toolchain setup (host c++ used, -mthumb fails).
        return join(dirname(_SCRIPTS_DIR), "builder", "board_build", "samd",
                    "samd_build.py")

    def arduino_script(self, env, board) -> str:
        # Relative to builder/frameworks/ (the framework script's dir).
        return "../board_build/samd/samd_arduino.py"

    # ------------------------------------------------------------------
    # Debug tools (called from platform.py get_boards)
    # ------------------------------------------------------------------

    def inject_debug_tools(self, board) -> None:
        debug = board.manifest.setdefault("debug", {})
        if "tools" in debug:
            return  # manifest already carries tool configs
        tools = debug.setdefault("tools", {})

        for link in ("blackmagic", "jlink", "cmsis-dap"):
            if link in tools:
                continue
            if link == "blackmagic":
                tools["blackmagic"] = {
                    "hwids": [["0x1d50", "0x6018"]],
                    "require_debug_port": True,
                }
            elif link == "jlink":
                assert debug.get("jlink_device"), (
                    "Missing J-Link Device ID for %s" % board.id
                )
                tools[link] = {
                    "server": {
                        "package": "tool-jlink",
                        "arguments": [
                            "-singlerun", "-if", "SWD", "-select", "USB",
                            "-device", debug.get("jlink_device"), "-port", "2331",
                        ],
                        "executable": (
                            "JLinkGDBServerCL.exe" if IS_WINDOWS else "JLinkGDBServer"
                        ),
                    }
                }
            else:
                chipname = debug.get("openocd_chipname")
                if not chipname:
                    continue
                tools[link] = {
                    "server": {
                        "package": "tool-openocd",
                        "executable": "bin/openocd",
                        "arguments": [
                            "-s", "$PACKAGE_DIR/openocd/scripts",
                            "-f", "interface/%s.cfg" % link,
                            "-c", "set CHIPNAME %s" % chipname,
                            "-f", "target/%s" % debug.get(
                                "openocd_target", chipname
                            ),
                        ],
                    }
                }
            tools[link]["onboard"] = link in debug.get("onboard_tools", [])
            tools[link]["default"] = link in debug.get("default_tools", [])

    def configure_debug_session(self, debug_config) -> None:
        if not debug_config.speed:
            return
        server = debug_config.server or {}
        exe = server.get("executable", "").lower()
        if "openocd" in exe:
            server.setdefault("arguments", []).extend(
                ["-c", "adapter speed %s" % debug_config.speed]
            )
        elif "jlink" in exe:
            server.setdefault("arguments", []).extend(
                ["-speed", debug_config.speed]
            )

    def configure_env(self, env, board) -> None:
        env.Append(CPPDEFINES=self.build_flags(board.manifest))
