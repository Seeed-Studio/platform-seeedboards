# Copyright 2026-present Seeed Studio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Raspberry Pi RP2040/RP2350 chip family.

Owns the package matrix (per-OS earlephilhower toolchain URLs, core
selection, J-Link trimming) and the default debug-tools table, inlined
from the retired platform_cfg/rpi_cfg.py, plus the upstream builder
lock: the board-level skeleton is the maxgerhardt/platform-raspberrypi
builder/main.py (official platformio/platform-raspberrypi is an mbed
shell without earlephilhower/RP2350/XIAO), executed by
builder/families/rpi/build.py, which PATH-prepends the earlephilhower
tool packages so the upstream bare tool names resolve.
"""

import sys
from os.path import join

from .base import ChipFamily

IS_WINDOWS = sys.platform.startswith("win")

# Runtime toolchain overrides (same mechanism as the maxgerhardt
# platform): the earlephilhower tools ship per-OS release assets, so
# the package spec is rewritten at configure time from these tables.
EARLE_TOOLCHAIN_ARM = {
    # Windows
    "windows_amd64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-w64-mingw32.arm-none-eabi-8ec9d6f.240929.zip",
    "windows_x86": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/i686-w64-mingw32.arm-none-eabi-8ec9d6f.240929.zip",
    # No Windows ARM64 or ARM32 builds.
    # Linux
    "linux_x86_64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-linux-gnu.arm-none-eabi-8ec9d6f.240929.tar.gz",
    "linux_i686": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/i686-linux-gnu.arm-none-eabi-8ec9d6f.240929.tar.gz",
    "linux_aarch64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-linux-gnu.arm-none-eabi-8ec9d6f.240929.tar.gz",
    "linux_armv7l": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/arm-linux-gnueabihf.arm-none-eabi-8ec9d6f.240929.tar.gz",
    "linux_armv6l": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/arm-linux-gnueabihf.arm-none-eabi-8ec9d6f.240929.tar.gz",
    # Mac (Intel and ARM are separate)
    "darwin_x86_64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-apple-darwin20.4.arm-none-eabi-8ec9d6f.240929.tar.gz",
    "darwin_arm64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-apple-darwin20.4.arm-none-eabi-8ec9d6f.240929.tar.gz",
}

EARLE_TOOLCHAIN_RISCV = {
    # Windows
    "windows_amd64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-w64-mingw32.riscv32-unknown-elf-8ec9d6f.240929.zip",
    "windows_x86": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/i686-w64-mingw32.riscv32-unknown-elf-8ec9d6f.240929.zip",
    # No Windows ARM64 or ARM32 builds.
    # Linux
    "linux_x86_64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-linux-gnu.riscv32-unknown-elf-8ec9d6f.240929.tar.gz",
    "linux_i686": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/i686-linux-gnu.riscv32-unknown-elf-8ec9d6f.240929.tar.gz",
    "linux_aarch64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-linux-gnu.riscv32-unknown-elf-8ec9d6f.240929.tar.gz",
    "linux_armv7l": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/arm-linux-gnueabihf.riscv32-unknown-elf-8ec9d6f.240929.tar.gz",
    "linux_armv6l": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/arm-linux-gnueabihf.riscv32-unknown-elf-8ec9d6f.240929.tar.gz",
    # Mac (Intel and ARM are separate)
    "darwin_x86_64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-apple-darwin20.4.riscv32-unknown-elf-8ec9d6f.240929.tar.gz",
    "darwin_arm64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-apple-darwin20.4.riscv32-unknown-elf-8ec9d6f.240929.tar.gz",
}

EARLE_OPENOCD = {
    # Windows
    "windows_amd64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-w64-mingw32.openocd-ebec9504d.240929.zip",
    "windows_x86": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/i686-w64-mingw32.openocd-ebec9504d.240929.zip",
    # No Windows ARM64 or ARM32 builds.
    # Linux
    "linux_x86_64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-linux-gnu.openocd-ebec9504d.240929.tar.gz",
    "linux_i686": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/i686-linux-gnu.openocd-ebec9504d.240929.tar.gz",
    "linux_aarch64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-linux-gnu.openocd-ebec9504d.240929.tar.gz",
    "linux_armv7l": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/arm-linux-gnueabihf.openocd-ebec9504d.240929.tar.gz",
    "linux_armv6l": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/arm-linux-gnueabihf.openocd-ebec9504d.240929.tar.gz",
    # Mac (Intel and ARM are separate)
    "darwin_x86_64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-apple-darwin20.4.openocd-ebec9504d.240929.tar.gz",
    "darwin_arm64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-apple-darwin20.4.openocd-ebec9504d.240929.tar.gz",
}

EARLE_PICOTOOL = {
    # Windows
    "windows_amd64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-w64-mingw32.picotool-8a9af99.240929.zip",
    "windows_x86": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/i686-w64-mingw32.picotool-8a9af99.240929.zip",
    # No Windows ARM64 or ARM32 builds.
    # Linux
    "linux_x86_64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-linux-gnu.picotool-8a9af99.240929.tar.gz",
    "linux_i686": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/i686-linux-gnu.picotool-8a9af99.240929.tar.gz",
    "linux_aarch64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-linux-gnu.picotool-8a9af99.240929.tar.gz",
    "linux_armv7l": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/arm-linux-gnueabihf.picotool-8a9af99.240929.tar.gz",
    "linux_armv6l": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/arm-linux-gnueabihf.picotool-8a9af99.240929.tar.gz",
    # Mac (Intel and ARM are separate)
    "darwin_x86_64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/x86_64-apple-darwin20.4.picotool-8a9af99.240929.tar.gz",
    "darwin_arm64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-apple-darwin20.4.picotool-8a9af99.240929.tar.gz",
}


class RpiFamily(ChipFamily):
    family_ids = ("rpi",)
    owned_packages = ("toolchain-rp2040-earlephilhower", "tool-jlink")

    # Personal fork: the official platformio/platform-raspberrypi is an
    # mbed-only shell (no earlephilhower core, no RP2350, no XIAO); the
    # real upstream is maxgerhardt's develop line. Locked at the fork
    # point where our local builder snapshot diverged (+17/-17, 5
    # hunks). Bus factor accepted: SHA lock; bumping to mg HEAD
    # (+574/-322, new tool-pioasm) is a separate lock-bump PR.
    upstream_platform = "raspberrypi"
    upstream_version = (
        "https://github.com/maxgerhardt/platform-raspberrypi.git"
        "#4d1ad09d78445f16688627de0819646fd655910e"  # v1.17.0 fork point
    )

    # -- package matrix --------------------------------------------------

    def configure_default_packages(self, platform, variables, targets):
        from platformio import util

        board = variables.get("board")
        board_config = platform.board_config(board)
        chip = variables.get("board_build.mcu", board_config.get("build.mcu"))
        build_core = variables.get(
            "board_build.core", board_config.get("build.core", "arduino"))
        # Use the same string identifier as seen in "pio system info"
        # and the registry
        sys_type = util.get_systype()
        frameworks = variables.get("pioframework", [])

        # Configure OpenOCD package if used
        openocd_pkg = "tool-openocd-rp2040-earlephilhower"
        platform.packages[openocd_pkg]["optional"] = False
        if openocd_pkg in platform.packages:
            platform.packages[openocd_pkg]["version"] = EARLE_OPENOCD[sys_type]
        picotool_pkg = "tool-picotool-rp2040-earlephilhower"
        platform.packages[picotool_pkg]["optional"] = False
        if picotool_pkg in platform.packages:
            platform.packages[picotool_pkg]["version"] = EARLE_PICOTOOL[sys_type]

        if "arduino" in frameworks:
            if build_core == "arduino":
                platform.frameworks["arduino"]["package"] = "framework-arduino-mbed"
                platform.packages["framework-arduinopico"]["optional"] = True
                platform.packages["toolchain-rp2040-earlephilhower"]["optional"] = True
                platform.packages.pop("toolchain-rp2040-earlephilhower", None)
            elif build_core == "earlephilhower":
                platform.frameworks["arduino"]["package"] = "framework-arduinopico"
                platform.packages["framework-arduino-mbed"]["optional"] = True
                # Leave toolchain-gccarmnoneeabi in place (it stays
                # optional, so it is never installed for rpi builds):
                # popping it from the shared dict breaks any later
                # in-process configuration of nrf/samd/siliconlab/
                # stm32/renesas boards that require it.
                platform.packages["toolchain-rp2040-earlephilhower"]["optional"] = False
                # Configure toolchain download link dynamically
                # RP2350 (RISC-V)
                if chip == "rp2350-riscv":
                    platform.packages["toolchain-rp2040-earlephilhower"][
                        "version"] = EARLE_TOOLCHAIN_RISCV[sys_type]
                # RP2040, RP2350 (ARM)
                else:
                    platform.packages["toolchain-rp2040-earlephilhower"][
                        "version"] = EARLE_TOOLCHAIN_ARM[sys_type]
            else:
                sys.stderr.write(
                    "Error! Unknown build.core value '%s'. Don't know which "
                    "Arduino core package to use." % build_core)
                sys.exit(1)

        # if we want to build a filesystem, we need the tools.
        if "buildfs" in targets:
            platform.packages[
                "tool-mklittlefs-rp2040-earlephilhower"]["optional"] = False

        # configure J-LINK tool
        jlink_conds = [
            "jlink" in variables.get(option, "")
            for option in ("upload_protocol", "debug_tool")
        ]
        if variables.get("board"):
            board_config = platform.board_config(variables.get("board"))
            jlink_conds.extend([
                "jlink" in board_config.get(key, "")
                for key in ("debug.default_tools", "upload.protocol")
            ])
        if not any(jlink_conds):
            self.drop_package(platform, "tool-jlink")

        # Every rpi build runs the upstream builder skeleton; make sure
        # the locked checkout is present.
        self._ensure_upstream_platform(platform)

    # -- debug -----------------------------------------------------------

    def add_default_debug_tools(self, platform, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get(
            "protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        for link in ("blackmagic", "cmsis-dap", "jlink", "raspberrypi-swd",
                     "picoprobe", "pico-debug"):
            if link not in upload_protocols or link in debug["tools"]:
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
                    },
                    "onboard": link in debug.get("onboard_tools", [])
                }
            elif link == "pico-debug":
                debug["tools"][link] = {
                    "server": {
                        "executable": "bin/openocd",
                        "package": "tool-openocd-rp2040-earlephilhower",
                        "arguments": [
                            "-s", "$PACKAGE_DIR/share/openocd/scripts",
                            "-f", "board/%s.cfg" % link,
                        ]
                    }
                }
            else:
                openocd_target = debug.get("openocd_target")
                assert openocd_target, ("Missing target configuration for %s" %
                                        board.id)
                debug["tools"][link] = {
                    "server": {
                        "executable": "bin/openocd",
                        "package": "tool-openocd-rp2040-earlephilhower",
                        "arguments": [
                            "-s", "$PACKAGE_DIR/share/openocd/scripts",
                            "-f", "interface/%s.cfg" % (
                                "cmsis-dap" if link == "picoprobe" else link),
                            "-f", "target/%s" % openocd_target
                        ]
                    }
                }

        board.manifest["debug"] = debug
        return board

    def configure_debug_session(self, platform, debug_config):
        is_riscv = False
        if "board_build.mcu" in debug_config.env_options:
            is_riscv = debug_config.env_options["board_build.mcu"] == "rp2350-riscv"
        adapter_speed = debug_config.speed or "1000"
        server_options = debug_config.server or {}
        server_arguments = server_options.get("arguments", [])
        # This is ugly but the only way I found this working.
        # We need to give OpenOCD the rp2350-riscv.cfg config if we're
        # in RISC-V mode (set dynamically by board_build.mcu =
        # rp2350-riscv in the platformio.ini of the project).
        # Somehow that can not yet be determined when we're inside
        # add_default_debug_tools(), so we have to patch this up
        # afterwards.
        if is_riscv:
            try:
                server_arguments[server_arguments.index(
                    "target/rp2350.cfg")] = "target/rp2350-riscv.cfg"
            except ValueError:
                pass
        if ("interface/cmsis-dap.cfg" in server_arguments
                or "interface/picoprobe.cfg" in server_arguments):
            server_arguments.extend(
                ["-c", "adapter speed %s" % adapter_speed]
            )
        elif "jlink" in server_options.get("executable", "").lower():
            server_arguments.extend(
                ["-speed", adapter_speed]
            )

    # -- builder side ----------------------------------------------------

    def build_script(self, platform, board):
        # host_dir(), not platform.get_dir(): resolving inside the
        # wrapped window would point at the upstream package.
        return join(self.host_dir(), "builder", "families", "rpi", "build.py")

    def framework_script(self, platform, framework, board):
        # The upstream arduino.py dispatches on build.core: the
        # earlephilhower branch is what our boards run (the retired
        # local rpi_arduino.py was exactly that branch); the mbed-core
        # branch is upstream's, for build.core == "arduino".
        if framework != "arduino":
            return None
        return join(self._upstream_platform_dir(),
                    "builder", "frameworks", "arduino", "arduino.py")
