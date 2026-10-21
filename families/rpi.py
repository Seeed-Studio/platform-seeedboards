"""Raspberry Pi RP2040/RP2350 family — earlephilhower Arduino core.

Adapted from the predecessor repo (itself aligned with the upstream
platform-raspberrypi current state). The earlephilhower quick-toolchain
tools have no registry entries: the family pins per-host-system release
URLs (pico-quick-toolchain 5.0.0) as version overrides.

The Arduino framework package is selected by the manifest through the
generic router (build.arduino.package -> framework-arduinopico).

A project may build the RP2350 in RISC-V mode via
``board_build.mcu = rp2350-riscv``; the toolchain override for that
lives here (required_packages reads the project variables), and
configure_debug_session rewrites the OpenOCD target accordingly.
"""

import sys
from os.path import dirname, join

from families.base import ChipFamily

_SCRIPTS_DIR = dirname(__file__)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

IS_WINDOWS = sys.platform.startswith("win")

_QTC = "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/5.0.0"

# Per-host-system tool URLs (pico-quick-toolchain 5.0.0). Keyed by the
# same system identifier `pio system info` and the registry use.
EARLE_TOOLCHAIN_ARM = {
    "windows_amd64": _QTC + "/x86_64-w64-mingw32.arm-none-eabi-78c24be.260719.zip",
    "windows_x86": _QTC + "/i686-w64-mingw32.arm-none-eabi-78c24be.260719.zip",
    "linux_x86_64": _QTC + "/x86_64-linux-gnu.arm-none-eabi-78c24be.260719.tar.gz",
    "linux_i686": _QTC + "/i686-linux-gnu.arm-none-eabi-78c24be.260719.tar.gz",
    "linux_aarch64": _QTC + "/aarch64-linux-gnu.arm-none-eabi-78c24be.260719.tar.gz",
    "linux_armv7l": _QTC + "/arm-linux-gnueabihf.arm-none-eabi-78c24be.260719.tar.gz",
    "linux_armv6l": _QTC + "/arm-linux-gnueabihf.arm-none-eabi-78c24be.260719.tar.gz",
    "darwin_x86_64": _QTC + "/x86_64-apple-darwin20.4.arm-none-eabi-78c24be.260719.tar.gz",
    "darwin_arm64": _QTC + "/aarch64-apple-darwin20.4.arm-none-eabi-78c24be.260719.tar.gz",
}

EARLE_TOOLCHAIN_RISCV = {
    "windows_amd64": _QTC + "/x86_64-w64-mingw32.riscv32-unknown-elf-78c24be.260719.zip",
    "windows_x86": _QTC + "/i686-w64-mingw32.riscv32-unknown-elf-78c24be.260719.zip",
    "linux_x86_64": _QTC + "/x86_64-linux-gnu.riscv32-unknown-elf-78c24be.260719.tar.gz",
    "linux_i686": _QTC + "/i686-linux-gnu.riscv32-unknown-elf-78c24be.260719.tar.gz",
    "linux_aarch64": _QTC + "/aarch64-linux-gnu.riscv32-unknown-elf-78c24be.260719.tar.gz",
    "linux_armv7l": _QTC + "/arm-linux-gnueabihf.riscv32-unknown-elf-78c24be.260719.tar.gz",
    "linux_armv6l": _QTC + "/arm-linux-gnueabihf.riscv32-unknown-elf-78c24be.260719.tar.gz",
    "darwin_x86_64": _QTC + "/x86_64-apple-darwin20.4.riscv32-unknown-elf-78c24be.260719.tar.gz",
    "darwin_arm64": _QTC + "/aarch64-apple-darwin20.4.riscv32-unknown-elf-78c24be.260719.tar.gz",
}

EARLE_OPENOCD = {
    "windows_amd64": _QTC + "/x86_64-w64-mingw32.openocd-acff23ffd.260719.zip",
    "windows_x86": _QTC + "/i686-w64-mingw32.openocd-acff23ffd.260719.zip",
    "linux_x86_64": _QTC + "/x86_64-linux-gnu.openocd-acff23ffd.260719.tar.gz",
    "linux_i686": _QTC + "/i686-linux-gnu.openocd-acff23ffd.260719.tar.gz",
    "linux_aarch64": _QTC + "/aarch64-linux-gnu.openocd-acff23ffd.260719.tar.gz",
    "linux_armv7l": _QTC + "/arm-linux-gnueabihf.openocd-acff23ffd.260719.tar.gz",
    "linux_armv6l": _QTC + "/arm-linux-gnueabihf.openocd-acff23ffd.260719.tar.gz",
    "darwin_x86_64": _QTC + "/x86_64-apple-darwin20.4.openocd-acff23ffd.260719.tar.gz",
    "darwin_arm64": _QTC + "/aarch64-apple-darwin20.4.openocd-acff23ffd.260719.tar.gz",
}

EARLE_PICOTOOL = {
    "windows_amd64": _QTC + "/x86_64-w64-mingw32.picotool-6f6458d.260719.zip",
    "windows_x86": _QTC + "/i686-w64-mingw32.picotool-6f6458d.260719.zip",
    "linux_x86_64": _QTC + "/x86_64-linux-gnu.picotool-6f6458d.260719.tar.gz",
    "linux_i686": _QTC + "/i686-linux-gnu.picotool-6f6458d.260719.tar.gz",
    "linux_aarch64": _QTC + "/aarch64-linux-gnu.picotool-6f6458d.260719.tar.gz",
    "linux_armv7l": _QTC + "/arm-linux-gnueabihf.picotool-6f6458d.260719.tar.gz",
    "linux_armv6l": _QTC + "/arm-linux-gnueabihf.picotool-6f6458d.260719.tar.gz",
    "darwin_x86_64": _QTC + "/x86_64-apple-darwin20.4.picotool-6f6458d.260719.tar.gz",
    "darwin_arm64": _QTC + "/aarch64-apple-darwin20.4.picotool-6f6458d.260719.tar.gz",
}

EARLE_PIOASM = {
    "windows_amd64": _QTC + "/x86_64-w64-mingw32.pioasm-98a542c1.260719.zip",
    "windows_x86": _QTC + "/i686-w64-mingw32.pioasm-98a542c1.260719.zip",
    "linux_x86_64": _QTC + "/x86_64-linux-gnu.pioasm-98a542c1.260719.tar.gz",
    "linux_i686": _QTC + "/i686-linux-gnu.pioasm-98a542c1.260719.tar.gz",
    "linux_aarch64": _QTC + "/aarch64-linux-gnu.pioasm-98a542c1.260719.tar.gz",
    "linux_armv7l": _QTC + "/arm-linux-gnueabihf.pioasm-98a542c1.260719.tar.gz",
    "linux_armv6l": _QTC + "/arm-linux-gnueabihf.pioasm-98a542c1.260719.tar.gz",
    "darwin_x86_64": _QTC + "/x86_64-apple-darwin20.4.pioasm-98a542c1.260719.tar.gz",
    "darwin_arm64": _QTC + "/aarch64-apple-darwin20.4.pioasm-98a542c1.260719.tar.gz",
}

# Debug links the family can synthesize servers for; gated on the
# manifest's upload.protocols.
DEBUG_LINKS = (
    "blackmagic", "cmsis-dap", "jlink", "raspberrypi-swd", "picoprobe",
    "pico-debug",
)


class RpiFamily(ChipFamily):
    family_ids = ("rpi",)

    def required_packages(self, board, variables=None) -> "dict[str, object]":
        build = board.get("build") or {}
        # board_build.mcu is a project-level override (rp2350-riscv).
        mcu = None
        if variables is not None:
            mcu = variables.get("board_build.mcu")
        mcu = mcu or build.get("mcu")

        # platformio is imported lazily: with the repo root on sys.path
        # (how core and the gates import families), a module-level
        # import would shadow the stdlib platform module.
        from platformio import util

        sys_type = util.get_systype()
        try:
            packages = {
                "framework-arduinopico": None,
                "tool-openocd-rp2040-earlephilhower": EARLE_OPENOCD[sys_type],
                "tool-picotool-rp2040-earlephilhower": EARLE_PICOTOOL[sys_type],
                # PIO assembler for .pio sources (upstream _build_pioasm.py).
                "tool-pioasm-rp2040-earlephilhower": EARLE_PIOASM[sys_type],
                # RP2350 (RISC-V) takes the RISC-V toolchain; RP2040 and
                # RP2350 (ARM) the arm-none-eabi one.
                "toolchain-rp2040-earlephilhower": (
                    EARLE_TOOLCHAIN_RISCV[sys_type]
                    if mcu == "rp2350-riscv" else EARLE_TOOLCHAIN_ARM[sys_type]
                ),
            }
        except KeyError:
            raise ValueError(
                "no earlephilhower quick-toolchain build for host system "
                "%r (families/rpi.py)" % sys_type
            )
        return packages

    def build_flags(self, board) -> list:
        return []

    def upload_protocol(self, board) -> str:
        return (board.get("upload") or {}).get("protocol", "picotool")

    def build_script(self, env, board) -> str:
        return join(dirname(_SCRIPTS_DIR), "builder", "board_build", "rpi",
                    "rpi_build.py")

    def arduino_script(self, env, board) -> str:
        return "../board_build/rpi/rpi_arduino.py"

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
                    "Missed J-Link Device ID for %s" % board.id)
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
                    },
                    "onboard": link in debug.get("onboard_tools", []),
                }
            elif link == "pico-debug":
                debug["tools"][link] = {
                    "server": {
                        "executable": "bin/openocd",
                        "package": "tool-openocd-rp2040-earlephilhower",
                        "arguments": [
                            "-s", "$PACKAGE_DIR/share/openocd/scripts",
                            "-f", "board/%s.cfg" % link,
                        ],
                    }
                }
            else:
                openocd_target = debug.get("openocd_target")
                assert openocd_target, (
                    "Missing target configuration for %s" % board.id)
                debug["tools"][link] = {
                    "server": {
                        "executable": "bin/openocd",
                        "package": "tool-openocd-rp2040-earlephilhower",
                        "arguments": [
                            "-s", "$PACKAGE_DIR/share/openocd/scripts",
                            "-f", "interface/%s.cfg" % (
                                "cmsis-dap" if link == "picoprobe" else link),
                            "-f", "target/%s" % openocd_target,
                        ],
                    }
                }

            debug["tools"][link].setdefault(
                "onboard", link in debug.get("onboard_tools", []))
            debug["tools"][link].setdefault(
                "default", link in debug.get("default_tools", []))

        board.manifest["debug"] = debug

    def configure_debug_session(self, debug_config) -> None:
        # board_build.mcu = rp2350-riscv switches the OpenOCD target to
        # the RISC-V config (the link value cannot be resolved during
        # inject_debug_tools, so it is patched up here).
        is_riscv = (
            debug_config.env_options.get("board_build.mcu") == "rp2350-riscv")
        adapter_speed = debug_config.speed or "1000"
        server_options = debug_config.server or {}
        server_arguments = server_options.get("arguments", [])
        if is_riscv:
            try:
                server_arguments[server_arguments.index("target/rp2350.cfg")] = (
                    "target/rp2350-riscv.cfg")
            except ValueError:
                pass  # keep the ARM config when the rewrite does not apply
        if ("interface/cmsis-dap.cfg" in server_arguments
                or "interface/picoprobe.cfg" in server_arguments):
            server_arguments.extend(
                ["-c", "adapter speed %s" % adapter_speed])
        elif "jlink" in server_options.get("executable", "").lower():
            server_arguments.extend(["-speed", adapter_speed])
