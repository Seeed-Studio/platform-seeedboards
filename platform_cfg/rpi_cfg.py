import sys
import platform
from platformio import util


earle_toolchain_arm = {
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
    "darwin_arm64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-apple-darwin20.4.arm-none-eabi-8ec9d6f.240929.tar.gz"
}

earle_toolchain_riscv = {
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
    "darwin_arm64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-apple-darwin20.4.riscv32-unknown-elf-8ec9d6f.240929.tar.gz"
}

earle_openocd = {
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
    "darwin_arm64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-apple-darwin20.4.openocd-ebec9504d.240929.tar.gz"
}

earle_picotool = {
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
    "darwin_arm64": "https://github.com/earlephilhower/pico-quick-toolchain/releases/download/4.0.1/aarch64-apple-darwin20.4.picotool-8a9af99.240929.tar.gz"
}


def configure_rpi_default_packages(self, variables, targets):
        #print("System type: %s" % (util.get_systype()))
        # configure arduino core package.
        # select the right one based on the build.core, disable other one.
        board = variables.get("board")
        board_config = self.board_config(board)
        chip = variables.get("board_build.mcu", board_config.get("build.mcu"))
        build_core = variables.get(
            "board_build.core", board_config.get("build.core", "arduino"))
        # Use the same string identifier as seen in "pio system info" and registry
        sys_type = util.get_systype()
        print("sys_type is:",sys_type)
        frameworks = variables.get("pioframework", [])
        # Configure OpenOCD package if used
        openocd_pkg = "tool-openocd-rp2040-earlephilhower"
        self.packages[openocd_pkg]["optional"] = False
        if openocd_pkg in self.packages:
            self.packages[openocd_pkg]["version"] = earle_openocd[sys_type]
        picotool_pkg = "tool-picotool-rp2040-earlephilhower"
        self.packages[picotool_pkg]["optional"] = False
        if picotool_pkg in self.packages:
            self.packages[picotool_pkg]["version"] = earle_picotool[sys_type]
        print("build_core =:",build_core,)
        if "arduino" in frameworks:
            if build_core == "arduino":
                self.frameworks["arduino"]["package"] = "framework-arduino-mbed"
                self.packages["framework-arduinopico"]["optional"] = True
                self.packages["toolchain-rp2040-earlephilhower"]["optional"] = True
                self.packages.pop("toolchain-rp2040-earlephilhower", None)
            elif build_core == "earlephilhower":
                self.frameworks["arduino"]["package"] = "framework-arduinopico"
                self.packages["framework-arduino-mbed"]["optional"] = True
                self.packages.pop("toolchain-gccarmnoneeabi", None)
                self.packages["toolchain-rp2040-earlephilhower"]["optional"] = False
                # Configure toolchain download link dynamically
                # RP2350 (RISC-V)
                print("chip =:",chip)
                if chip == "rp2350-riscv":
                    self.packages["toolchain-rp2040-earlephilhower"]["version"] = earle_toolchain_riscv[sys_type]
                # RP2040, RP2350 (ARM)
                else:
                    self.packages["toolchain-rp2040-earlephilhower"]["version"] = earle_toolchain_arm[sys_type]
            else:
                sys.stderr.write(
                    "Error! Unknown build.core value '%s'. Don't know which Arduino core package to use." % build_core)
                env.Exit(1)

        # if we want to build a filesystem, we need the tools.
        if "buildfs" in targets:
            self.packages["tool-mklittlefs-rp2040-earlephilhower"]["optional"] = False

        # configure J-LINK tool
        jlink_conds = [
            "jlink" in variables.get(option, "")
            for option in ("upload_protocol", "debug_tool")
        ]
        if variables.get("board"):
            board_config = self.board_config(variables.get("board"))
            jlink_conds.extend([
                "jlink" in board_config.get(key, "")
                for key in ("debug.default_tools", "upload.protocol")
            ])
        jlink_pkgname = "tool-jlink"
        if not any(jlink_conds) and jlink_pkgname in self.packages:
            del self.packages[jlink_pkgname]


def _add_rpi_default_debug_tools(self, board):
        debug = board.manifest.get("debug", {})
        upload_protocols = board.manifest.get("upload", {}).get(
            "protocols", [])
        if "tools" not in debug:
            debug["tools"] = {}

        for link in ("blackmagic", "cmsis-dap", "jlink", "raspberrypi-swd", "picoprobe", "pico-debug"):
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
                                       if platform.system() == "Windows" else
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
                            "-f", "interface/%s.cfg" % ("cmsis-dap" if link == "picoprobe" else link),
                            "-f", "target/%s" % openocd_target
                        ]
                    }
                }

        board.manifest["debug"] = debug
        return board


def configure_rpi_debug_session(self, debug_config):
        is_riscv = False
        if "board_build.mcu" in debug_config.env_options:
            is_riscv = debug_config.env_options["board_build.mcu"] == "rp2350-riscv"
        adapter_speed = debug_config.speed or "1000"
        server_options = debug_config.server or {}
        server_arguments:list[str] = server_options.get("arguments", [])
        # This is ugly but the only way I found this to be working.
        # We need to give OpenOCD the rp2350-riscv.cfg config if we're in RISC-V mode
        # (set dynamically by board_build.mcu = rp2350-riscv in the platformio.ini of the project)
        # Somehow that can not yet be determined when we're inside _add_default_debug_tools(),
        # So we have to patch this up afterwards.
        if is_riscv:
            try:
                server_arguments[server_arguments.index("target/rp2350.cfg")] = "target/rp2350-riscv.cfg"
            except:
                pass
        if "interface/cmsis-dap.cfg" in server_arguments or "interface/picoprobe.cfg" in server_arguments:
            server_arguments.extend(
                ["-c", "adapter speed %s" % adapter_speed]
            )
        elif "jlink" in server_options.get("executable", "").lower():
            server_arguments.extend(
                ["-speed", adapter_speed]
            )
