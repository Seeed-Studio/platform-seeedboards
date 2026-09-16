# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Attribution:
# ESP32-related package, debug-tool, and debug-session configuration in
# this file is based in part on pioarduino project work:
# https://github.com/pioarduino/platform-espressif32
# Modified by Seeed Studio.
#
# Contract with platform.py (thin shim): the three hooks
# configure_esp_default_packages, _add_esp_default_debug_tools, and
# configure_esp_debug_session are resolved by build.family == "esp".

import json
import logging
import os
import shutil
import struct
import subprocess
from importlib import import_module
from pathlib import Path

from platformio.compat import IS_WINDOWS
from platformio.package.manager.tool import ToolPackageManager
from platformio.proc import get_pythonexe_path
from platformio.project.config import ProjectConfig
from platformio.public import to_unix_path


logger = logging.getLogger(__name__)

DEFAULT_DEBUG_SPEED = "5000"
DEFAULT_APP_OFFSET = "0x10000"

# MCUs that support the ESP-builtin (USB JTAG) debug tool.
# Refreshed from pioarduino ESP_BUILTIN_DEBUG_MCUS (esp32c5 included).
ESP_BUILTIN_DEBUG_MCUS = frozenset([
    "esp32c3", "esp32c5", "esp32c6", "esp32c61", "esp32s3", "esp32h2", "esp32p4"
])

# MCU -> toolchain mapping, refreshed from pioarduino MCU_TOOLCHAIN_CONFIG.
# Each architecture names its compiler toolchain and GDB package pair.
MCU_TOOLCHAIN_CONFIG = {
    "xtensa": {
        "mcus": frozenset(["esp32", "esp32s2", "esp32s3"]),
        "toolchains": ["toolchain-xtensa-esp-elf", "tool-xtensa-esp-elf-gdb"],
    },
    "riscv": {
        "mcus": frozenset([
            "esp32c2", "esp32c3", "esp32c5", "esp32c6", "esp32c61", "esp32h2",
            "esp32p4"
        ]),
        "toolchains": ["toolchain-riscv32-esp", "tool-riscv32-esp-elf-gdb"],
    },
}


def configure_esp_default_packages(self, variables, targets):
    board_config = self.board_config(variables.get("board"))
    mcu = variables.get("board_build.mcu", board_config.get("build.mcu", "esp32"))
    frameworks = list(variables.get("pioframework", []))

    def _mark_required(package_name):
        if package_name in self.packages:
            self.packages[package_name]["optional"] = False

    if "arduino" in frameworks:
        _mark_required("framework-arduinoespressif32")
        _mark_required("framework-arduinoespressif32-libs")
        # esp32c2 / esp32c61 have no prebuilt Arduino libs; skeleton
        # packages provide the minimal compile stubs.
        if mcu == "esp32c2":
            _mark_required("framework-arduino-c2-skeleton-lib")
        if mcu == "esp32c61":
            _mark_required("framework-arduino-c61-skeleton-lib")

    if "espidf" in frameworks:
        _mark_required("framework-espidf")
        # Common ESP-IDF build tools (upstream COMMON_IDF_PACKAGES).
        for package in ("tool-cmake", "tool-ninja", "tool-scons"):
            _mark_required(package)

    _mark_required("tool-esptoolpy")

    # Enable check tools only when "check_tool" is enabled.
    # self.packages mirrors the packages section of platform.json.
    for p in self.packages:
        if p in ("tool-cppcheck", "tool-clangtidy", "tool-pvs-studio"):
            self.packages[p]["optional"] = (
                False
                if str(variables.get("check_tool")).strip("['']") in p
                else True
            )

    # Xtensa MCUs need the Xtensa toolchain; drop it for every other MCU.
    if mcu in MCU_TOOLCHAIN_CONFIG["xtensa"]["mcus"]:
        _mark_required("toolchain-xtensa-esp-elf")
    else:
        self.packages.pop("toolchain-xtensa-esp-elf", None)

    # RISC-V toolchain: required for RISC-V MCUs and for the RISC-V ULP
    # coprocessor of the ESP32-S2/S3 (pioarduino keeps it for both).
    if mcu in MCU_TOOLCHAIN_CONFIG["riscv"]["mcus"] or mcu in ("esp32s2", "esp32s3"):
        _mark_required("toolchain-riscv32-esp")

    # RISC-V-only MCUs have no Xtensa ULP coprocessor.
    if mcu in MCU_TOOLCHAIN_CONFIG["riscv"]["mcus"]:
        self.packages.pop("toolchain-esp32ulp", None)

    # Require both ESP GDB packages regardless of MCU architecture.
    for gdb_package in ("tool-xtensa-esp-elf-gdb", "tool-riscv32-esp-elf-gdb"):
        _mark_required(gdb_package)

    # ROM ELF files: espidf.py references this package via ESP_ROM_ELF_DIR
    # during ESP-IDF builds; pioarduino installs it for all ESP builds.
    _mark_required("tool-esp-rom-elfs")

    # ESP tool installation (pioarduino install_tool semantics): tools
    # shipped as tools.json stubs are expanded via idf_tools.py into the
    # core tools dir and re-installed as the package; already-expanded
    # tools are version-checked and preferred over the registry pins.
    _ensure_esptoolpy_runtime_dependencies(self)
    _prepare_esp_tools(self)


#
# ESP tool expansion helpers (tool-esp_install / idf_tools.py based).
#


def _iter_required_esp_tools(platform):
    return [
        name
        for name, options in platform.packages.items()
        if name != "tool-esp_install"
        and name.startswith(("tool-", "toolchain-"))
        and not options.get("optional", True)
    ]


def _get_packages_dir(platform):
    return ProjectConfig.get_instance().get("platformio", "packages_dir")


def _get_core_dir(platform):
    return ProjectConfig.get_instance().get("platformio", "core_dir")


def _prepare_esp_tools(platform):
    """Install/expand every esp tool required by this build.

    Mirrors pioarduino's install_tool(): a freshly downloaded stub
    package (tools.json, no payload) is expanded via idf_tools.py and
    the expanded content replaces the package; an already-expanded tool
    is version-checked against the platform.json pin and the package is
    re-pointed at the local directory.
    """
    packages_dir = Path(_get_packages_dir(platform))
    if not packages_dir.exists():
        return

    _ensure_esp_installer(platform, packages_dir)

    for tool_name in _iter_required_esp_tools(platform):
        _install_esp_tool(platform, tool_name, packages_dir)


def _ensure_esp_installer(platform, packages_dir):
    """Make sure tool-esp_install (idf_tools.py) is present."""
    installer = packages_dir / "tool-esp_install" / "tools" / "idf_tools.py"
    if installer.exists():
        return
    version = platform.packages.get("tool-esp_install", {}).get("version")
    if not version:
        return
    try:
        ToolPackageManager().install(version)
    except Exception as exc:  # pylint: disable=broad-except
        print("Warning: failed to install tool-esp_install: %s" % exc)


def _ensure_esptoolpy_runtime_dependencies(platform):
    """Install the pip modules esptool needs into the penv (once per process)."""
    if getattr(platform, "_esp_python_deps_prepared", False):
        return
    platform._esp_python_deps_prepared = True

    python_exe = get_pythonexe_path()
    if not python_exe:
        return
    # esptool runs from the $PYTHONEXE (penv) python with the
    # tool-esptoolpy dir on PYTHONPATH. That tool copy is expanded by
    # idf_tools.py and brings no bundled Python deps, so install the
    # optional runtime modules it imports: rich_click (CLI formatting)
    # and intelhex (image merge / bootloader.bin generation).
    for dep, module in (("rich_click<2", "rich_click"), ("intelhex", "intelhex")):
        try:
            import_module(module)
        except ImportError:
            try:
                subprocess.run(
                    [
                        python_exe,
                        "-m",
                        "pip",
                        "install",
                        dep,
                        "--disable-pip-version-check",
                        "--no-input",
                    ],
                    check=True,
                )
            except Exception as exc:  # pylint: disable=broad-except
                print("Warning: failed to install %s for esptoolpy: %s" % (dep, exc))


def _install_esp_tool(platform, tool_name, packages_dir, _reinstall=False):
    platform.packages[tool_name]["optional"] = False
    core_dir = Path(_get_core_dir(platform))
    tool_path = packages_dir / tool_name
    tools_json = tool_path / "tools.json"

    # idf_tools.py installs relative to IDF_TOOLS_PATH; keep it pinned to
    # the PlatformIO core dir for every invocation (pioarduino does the
    # same at module import time).
    os.environ["IDF_TOOLS_PATH"] = str(core_dir)
    os.environ["IDF_PATH"] = ""

    # Case 1: freshly downloaded stub -- expand and replace the package.
    if tools_json.exists():
        installer = packages_dir / "tool-esp_install" / "tools" / "idf_tools.py"
        if not installer.exists():
            print("Warning: idf_tools.py not found, cannot expand %s" % tool_name)
            return False
        result = subprocess.run(
            [
                get_pythonexe_path(),
                str(installer),
                "--quiet",
                "--non-interactive",
                "--tools-json",
                str(tools_json),
                "install",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip()[-1000:]
            print(
                "Warning: idf_tools.py install failed for %s: %s"
                % (tool_name, tail)
            )
            return False

        expanded = core_dir / "tools" / tool_name
        try:
            shutil.copy2(
                tool_path / "package.json", expanded / "package.json"
            )
            shutil.rmtree(tool_path)
            ToolPackageManager().install("file://%s" % expanded)
        except OSError as exc:
            print(
                "Warning: failed to install expanded tool %s: %s"
                % (tool_name, exc)
            )
            return False
        print("Expanded esp tool %s via idf_tools.py" % tool_name)
        platform.packages[tool_name]["version"] = str(tool_path)
        return True

    # Case 2: already expanded -- validate the version and prefer local.
    if tool_path.is_dir():
        required = platform.packages.get(tool_name, {}).get("package-version")
        installed = None
        try:
            installed = json.loads(
                (tool_path / "package.json").read_text(encoding="utf-8")
            ).get("version")
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        if required and installed != required and not _reinstall:
            print(
                "Version mismatch for %s (%s != %s); reinstalling"
                % (tool_name, installed, required)
            )
            shutil.rmtree(tool_path, ignore_errors=True)
            ToolPackageManager().install(
                str(platform.packages[tool_name].get("version", ""))
            )
            return _install_esp_tool(
                platform, tool_name, packages_dir, _reinstall=True
            )
        platform.packages[tool_name]["version"] = str(tool_path)
        return True

    return True


    return changed


#
# Dynamic board options (debug tool injection), refreshed from pioarduino
# _add_dynamic_options.
#


def _get_openocd_interface(link):
    """Resolve the OpenOCD interface identifier for a debug link."""
    if link in ("jlink", "cmsis-dap"):
        return link
    if link in ("esp-prog", "ftdi"):
        return "ftdi/esp_ftdi"
    if link in ("esp-prog-2", "esp-bridge"):
        return "esp_usb_bridge"
    if link == "esp-builtin":
        return "esp_usb_jtag"
    return "ftdi/" + link


def _get_debug_server_args(openocd_interface, debug):
    """Generate debug server arguments for OpenOCD configuration."""
    if "openocd_target" in debug:
        config_type = "target"
        config_name = debug.get("openocd_target")
    else:
        config_type = "board"
        config_name = debug.get("openocd_board")
    return [
        "-s",
        "$PACKAGE_DIR/share/openocd/scripts",
        "-f",
        "interface/%s.cfg" % openocd_interface,
        "-f",
        "%s/%s" % (config_type, config_name),
    ]


def _add_esp_default_debug_tools(self, board):
    # upload protocols
    if not board.get("upload.protocols", []):
        board.manifest["upload"]["protocols"] = ["esptool", "espota"]
    if not board.get("upload.protocol", ""):
        board.manifest["upload"]["protocol"] = "esptool"

    # debug tools
    debug = board.manifest.get("debug", {})
    non_debug_protocols = ["esptool", "espota"]
    supported_debug_tools = [
        "cmsis-dap",
        "esp-prog",
        "esp-prog-2",
        "esp-bridge",
        "iot-bus-jtag",
        "jlink",
        "minimodule",
        "olimex-arm-usb-tiny-h",
        "olimex-arm-usb-ocd-h",
        "olimex-arm-usb-ocd",
        "olimex-jtag-tiny",
        "tumpa",
    ]

    mcu = board.get("build.mcu", "")
    if mcu in ESP_BUILTIN_DEBUG_MCUS:
        supported_debug_tools.append("esp-builtin")

    # Auto-assign SVD path based on MCU if not already set. Guarded on
    # get_dir(): the hook is also exercised with bare stub objects.
    get_dir = getattr(self, "get_dir", None)
    if debug and not debug.get("svd_path") and callable(get_dir):
        svd_file = Path(get_dir()) / "misc" / "svd" / ("%s.svd" % mcu)
        if svd_file.is_file():
            debug["svd_path"] = str(svd_file)

    upload_protocol = board.manifest.get("upload", {}).get("protocol")
    upload_protocols = board.manifest.get("upload", {}).get("protocols", [])

    if debug:
        upload_protocols.extend(supported_debug_tools)
    if upload_protocol and upload_protocol not in upload_protocols:
        upload_protocols.append(upload_protocol)
    board.manifest["upload"]["protocols"] = upload_protocols

    if "tools" not in debug:
        debug["tools"] = {}

    for link in upload_protocols:
        if link in non_debug_protocols or link in debug["tools"]:
            continue

        openocd_interface = _get_openocd_interface(link)
        server_args = _get_debug_server_args(openocd_interface, debug)

        init_cmds = [
            "define pio_reset_halt_target",
            "   monitor reset halt",
            "   maintenance flush register-cache",
            "end",
            "define pio_reset_run_target",
            "   monitor reset",
            "end",
        ]
        init_cmds.extend([
            "target extended-remote $DEBUG_PORT",
            "$LOAD_CMDS",
            "pio_reset_halt_target",
            "$INIT_BREAK",
        ])

        debug["tools"][link] = {
            "server": {
                "package": "tool-openocd-esp32",
                "executable": "bin/openocd",
                "arguments": server_args,
            },
            "init_break": "thb app_main",
            "init_cmds": init_cmds,
            "onboard": link in debug.get("onboard_tools", []),
            "default": link == debug.get("default_tool"),
        }

    board.manifest["debug"] = debug
    return board


#
# Debug session configuration, refreshed from pioarduino
# configure_debug_session.
#


def _get_mcu_config(mcu):
    for config in MCU_TOOLCHAIN_CONFIG.values():
        if mcu in config["mcus"]:
            result = dict(config)
            result["ulp_toolchain"] = ["toolchain-esp32ulp"]
            if mcu != "esp32":
                result["ulp_toolchain"].append("toolchain-riscv32-esp")
            return result
    return None


def _gdb_has_python(self, mcu):
    """True when the MCU's GDB executable supports embedded Python."""
    mcu_config = _get_mcu_config(mcu)
    if not mcu_config:
        return False
    gdb_tools = [tool for tool in mcu_config["toolchains"] if "gdb" in tool]
    for tool_pkg in gdb_tools:
        pkg_dir = self.get_package_dir(tool_pkg)
        if not pkg_dir:
            continue
        is_xtensa = mcu in MCU_TOOLCHAIN_CONFIG["xtensa"]["mcus"]
        if is_xtensa:
            # Per-target binary first, then the generic name
            arch_prefixes = ["xtensa-%s-elf" % mcu, "xtensa-esp-elf"]
        else:
            arch_prefixes = ["riscv32-esp-elf"]
        candidates = []
        for prefix in arch_prefixes:
            if IS_WINDOWS:
                candidates.append(Path(pkg_dir) / "bin" / ("%s-gdb.exe" % prefix))
            candidates.append(Path(pkg_dir) / "bin" / ("%s-gdb" % prefix))
        gdb_path = next((path for path in candidates if path.is_file()), None)
        if not gdb_path:
            continue
        try:
            result = subprocess.run(
                [str(gdb_path), "--batch-silent", "--ex", "python import os"],
                capture_output=True, timeout=10,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            logger.debug("GDB Python support probe failed for %s", gdb_path)
            return False
    return False


def _get_freertos_gdb_cmds():
    """GDB commands that load the FreeRTOS thread-awareness extension."""
    # Use single-line try/except to survive cleanup_cmds stripping indentation
    return [
        "python",
        "try: import freertos_gdb",
        'except ModuleNotFoundError: print(\'warning: python extension "freertos_gdb" not found.\')',
        "end",
    ]


def _get_rom_elf_gdb_cmds(self, mcu):
    """GDB commands that load ROM ELF symbols for the given MCU.

    Builds a `target hookpost-extended-remote` hook using ROM metadata
    (misc/roms.json) and installed ROM ELF artifacts (tool-esp-rom-elfs).
    Returns [] when the metadata or the package is not available.
    """
    rom_elfs_dir = self.get_package_dir("tool-esp-rom-elfs")
    if not rom_elfs_dir or not Path(rom_elfs_dir).is_dir():
        return []

    roms_json = Path(self.get_dir()) / "misc" / "roms.json"
    if not roms_json.is_file():
        return []

    try:
        with open(roms_json, encoding="utf-8") as f:
            roms = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    if mcu not in roms:
        return []

    rom_elfs_path = to_unix_path(str(Path(rom_elfs_dir).resolve()))
    if not rom_elfs_path.endswith("/"):
        rom_elfs_path += "/"

    entries = roms[mcu]
    cmds = [
        "define target hookpost-extended-remote",
        "set confirm off",
    ]
    cmds.extend(_build_rom_elf_conditions(entries, mcu, rom_elfs_path, depth=1))
    cmds.extend([
        "set confirm on",
        "end",
    ])
    return cmds


def _rom_date_condition(date_addr, date_str):
    """A GDB `if` expression matching a ROM build-date string in memory."""
    parts = []
    for i in range(0, len(date_str), 4):
        chunk = date_str[i:i + 4]
        value = hex(struct.unpack("<I", chunk.encode("utf-8").ljust(4, b"\x00"))[0])
        parts.append("(*(int*) %s) == %s" % (hex(date_addr + i), value))
    return "if " + " && ".join(parts)


def _build_rom_elf_conditions(entries, mcu, rom_dir, depth):
    """Nested if/else/end GDB blocks loading the matching ROM ELF."""
    if not entries:
        return []
    indent = "  " * depth
    entry = entries[0]
    addr = int(entry["build_date_str_addr"], 16)
    rom_file = "%s_rev%s_rom.elf" % (mcu, entry["rev"])
    rom_path = "%s%s" % (rom_dir, rom_file)
    lines = [
        "%s%s" % (indent, _rom_date_condition(addr, entry["build_date_str"])),
        '%s  add-symbol-file "%s"' % (indent, rom_path),
    ]
    if len(entries) > 1:
        lines.append("%selse" % indent)
        lines.extend(_build_rom_elf_conditions(entries[1:], mcu, rom_dir, depth + 1))
    else:
        lines.append("%selse" % indent)
        lines.append("%s  echo Warning: Unknown %s ROM revision.\\n" % (indent, mcu))
    lines.append("%send" % indent)
    return lines


def _inject_debug_extensions(self, debug_config):
    """Insert FreeRTOS and ROM-ELF GDB commands before target attach."""
    mcu = debug_config.board_config.get("build.mcu", "")
    if not mcu:
        return
    tool_init_cmds = debug_config.tool_settings.get("init_cmds")
    if tool_init_cmds is None:
        return
    # Find insertion point: just before "target extended-remote"
    insert_idx = next(
        (i for i, cmd in enumerate(tool_init_cmds)
         if "target extended-remote" in cmd),
        len(tool_init_cmds),
    )
    extra_cmds = []
    if _gdb_has_python(self, mcu):
        extra_cmds.extend(_get_freertos_gdb_cmds())
    extra_cmds.extend(_get_rom_elf_gdb_cmds(self, mcu))
    for i, cmd in enumerate(extra_cmds):
        tool_init_cmds.insert(insert_idx + i, cmd)


def configure_esp_debug_session(self, debug_config):
    _inject_debug_extensions(self, debug_config)

    build_extra_data = debug_config.build_data.get("extra", {})
    flash_images = build_extra_data.get("flash_images", [])

    if "openocd" in (debug_config.server or {}).get("executable", ""):
        debug_config.server["arguments"].extend([
            "-c",
            "adapter speed %s" % (debug_config.speed or DEFAULT_DEBUG_SPEED),
        ])

    if debug_config.load_cmds != ["load"]:
        return

    ignore_conds = [
        not flash_images,
        not all([os.path.isfile(item["path"]) for item in flash_images]),
    ]

    if any(ignore_conds):
        logger.warning(
            "Falling back to default GDB load; "
            "flash_images metadata missing or incomplete."
        )
        return

    load_cmds = [
        'monitor program_esp "{{{path}}}" {offset} verify'.format(
            path=to_unix_path(item["path"]), offset=item["offset"]
        )
        for item in flash_images
    ]
    app_offset = build_extra_data.get("application_offset")
    if not app_offset:
        logger.warning(
            "Application offset not found in build metadata, "
            "falling back to default %s. Debug flashing may target "
            "the wrong address for custom partition layouts.",
            DEFAULT_APP_OFFSET,
        )
        app_offset = DEFAULT_APP_OFFSET
    load_cmds.append(
        'monitor program_esp "{%s.bin}" %s verify'
        % (
            to_unix_path(debug_config.build_data["prog_path"][:-4]),
            app_offset,
        )
    )
    debug_config.load_cmds = load_cmds
