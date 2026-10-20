"""ESP32 family (C3/C5/C6/S2/S3) — ChipFamily implementation.

Adapted from pioarduino/platform-espressif32 current state. The stub
package expansion (tool-esptoolpy et al. shipped as tools.json stubs,
expanded at build time via tool-esp_install/idf_tools.py) is the
ADR-0002 collision test case: the ESP packages land in platform.json
as stub zips, and every family that requires them must be able to
expand them (or the package moves to the registry).
"""

import sys
from os.path import dirname, join

from families.base import ChipFamily

_SCRIPTS_DIR = dirname(__file__)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


# ESP32 MCUs by architecture (upstream MCU_TOOLCHAIN_CONFIG)
XTESA_MCUS = frozenset(["esp32", "esp32s2", "esp32s3"])
RISCV_MCUS = frozenset(["esp32c2", "esp32c3", "esp32c5", "esp32c6", "esp32h2", "esp32p4"])
# MCUs with built-in USB JTAG debug (esp-builtin tool)
ESP_BUILTIN_MCUS = ("esp32c3", "esp32c5", "esp32c6", "esp32s3", "esp32h2")

# esptool runtime deps are pip-installed into the penv at most once per
# process (multi-env builds call configure_default_packages repeatedly).
_ESPTOOLPY_DEPS_PREPARED = False


class EspFamily(ChipFamily):
    family_ids = ("esp32",)

    def required_packages(self, board) -> "dict[str, object]":
        mcu = (board.get("build") or {}).get("mcu", "esp32")
        packages = {
            "framework-arduinoespressif32": None,
            "framework-arduinoespressif32-libs": None,
            "tool-esptoolpy": None,
            "tool-esp_install": None,
            "tool-esp-rom-elfs": None,
            "tool-xtensa-esp-elf-gdb": None,
            "tool-riscv32-esp-elf-gdb": None,
            # Shared build tools: registry pins for all families (the
            # pioarduino stub zigs need family-specific expansion that
            # the samd family never runs -- ADR-0002 single-slot rule).
            "tool-cmake": "~3.30.2",
            "tool-ninja": "^1.7.0",
            "tool-scons": None,
        }
        if mcu in XTESA_MCUS:
            packages["toolchain-xtensa-esp-elf"] = None
            # S2/S3 carry a RISC-V ULP coprocessor; pioarduino keeps
            # the RISC-V toolchain for both (upstream MCU_TOOLCHAIN_CONFIG).
            if mcu in ("esp32s2", "esp32s3"):
                packages["toolchain-riscv32-esp"] = None
        elif mcu in RISCV_MCUS:
            packages["toolchain-riscv32-esp"] = None
        else:
            raise ValueError(
                "unsupported ESP MCU %r (families/esp.py required_packages)"
                % mcu
            )
        return packages

    def build_flags(self, board) -> list:
        build = board.get("build") or {}
        mcu = build.get("mcu", "")
        flags = ["-DARDUINO_ARCH_ESP32", "-DESPLATFORMIO_BUILD"]
        extra = build.get("extra_flags", [])
        if isinstance(extra, str):
            flags.append(extra)
        else:
            flags.extend(extra)
        return flags

    def upload_protocol(self, board) -> str:
        return (board.get("upload") or {}).get("protocol", "esptool")

    def build_script(self, env, board) -> str:
        return join(dirname(_SCRIPTS_DIR), "builder", "board_build", "esp",
                    "esp_build.py")

    def arduino_script(self, env, board) -> str:
        return "../board_build/esp/esp_arduino.py"

    def inject_debug_tools(self, board) -> None:
        debug = board.manifest.setdefault("debug", {})
        if "tools" in debug:
            return
        tools = debug.setdefault("tools", {})
        supported = [
            "cmsis-dap", "esp-prog", "esp-bridge", "iot-bus-jtag", "jlink",
            "minimodule", "olimex-arm-usb-tiny-h", "olimex-arm-usb-ocd-h",
            "olimex-arm-usb-ocd", "olimex-jtag-tiny", "tumpa",
        ]
        mcu = (board.get("build") or board.manifest.get("build", {})).get("mcu", "")
        if mcu in ESP_BUILTIN_MCUS:
            supported.append("esp-builtin")

        openocd_target = debug.get("openocd_target")
        openocd_board = debug.get("openocd_board")

        for link in supported:
            if link in tools:
                continue
            if link in ("jlink", "cmsis-dap"):
                interface = link
            elif link in ("esp-prog", "ftdi"):
                interface = "ftdi/esp32_devkitj_v1"
            elif link == "esp-bridge":
                interface = "esp_usb_bridge"
            elif link == "esp-builtin":
                interface = "esp_usb_jtag"
            else:
                interface = "ftdi/%s" % link

            server_args = [
                "-s", "$PACKAGE_DIR/share/openocd/scripts",
                "-f", "interface/%s.cfg" % interface,
            ]
            if openocd_target:
                server_args.extend(["-f", "target/%s" % openocd_target])
            elif openocd_board:
                server_args.extend(["-f", "board/%s" % openocd_board])

            tools[link] = {
                "server": {
                    "package": "tool-openocd-esp32",
                    "executable": "bin/openocd",
                    "arguments": server_args,
                },
                "init_break": "thb app_main",
                "onboard": link in debug.get("onboard_tools", []),
                "default": link == debug.get("default_tool"),
            }

    def configure_debug_session(self, debug_config) -> None:
        if not debug_config.speed:
            return
        server = debug_config.server or {}
        if "openocd" in server.get("executable", "").lower():
            server.setdefault("arguments", []).extend(
                ["-c", "adapter speed %s" % (debug_config.speed or "5000")]
            )

    def configure_env(self, env, board) -> None:
        env.Append(CPPDEFINES=self.build_flags(board.manifest))

    def post_activate_packages(self, platform) -> bool:
        """Expand tools.json stub packages via tool-esp_install (ADR-0002).

        Runs AFTER super().configure_default_packages() so the stubs are
        already downloaded. Each stub is expanded via idf_tools.py into
        the core tools dir, then re-installed as the package (replacing
        the stub). ToolPackageManager.install() is what makes the result
        visible to core: it writes the .piopm marker and refreshes the
        per-process package cache -- a bare copytree of the expanded
        tree leaves the package invisible to get_package_dir().
        Already-expanded tools are re-pinned to their local package dir
        so the registry stub pin never overwrites them. Returns True so
        a second super() re-resolves with the local paths.
        """
        import os
        from pathlib import Path

        from platformio.project.config import ProjectConfig

        config = ProjectConfig.get_instance()
        packages_dir = Path(config.get("platformio", "packages_dir"))
        core_dir = Path(config.get("platformio", "core_dir"))

        if not self._ensure_esp_installer(platform, packages_dir):
            return False

        # idf_tools.py installs relative to IDF_TOOLS_PATH; keep it pinned
        # to the PlatformIO core dir for every invocation.
        os.environ["IDF_TOOLS_PATH"] = str(core_dir)
        os.environ["IDF_PATH"] = ""

        self._ensure_esptoolpy_runtime_dependencies()

        modified = False
        for tool_name in list(platform.packages):
            if not tool_name.startswith(("tool-", "toolchain-")):
                continue
            if tool_name == "tool-esp_install":
                continue
            if platform.packages[tool_name].get("optional", True):
                continue
            if self._install_esp_tool(platform, tool_name, packages_dir, core_dir):
                modified = True
        return modified

    def _install_esp_tool(self, platform, tool_name, packages_dir, core_dir,
                          _reinstall=False) -> bool:
        """Expand one stub package or re-pin an already-expanded one.

        Mirrors pioarduino's install_tool semantics:
        Case 1 -- fresh stub (tools.json present): expand via idf_tools.py,
        then re-install the expanded content as the package and re-pin the
        platform version to the local package dir.
        Case 2 -- already expanded: validate against the package-version
        pin; on drift, refetch the stub and re-expand, otherwise prefer
        the local package over the registry pin.
        """
        import json
        import shutil
        import subprocess

        from platformio.package.manager.tool import ToolPackageManager
        from platformio.proc import get_pythonexe_path

        platform.packages[tool_name]["optional"] = False
        pkg_dir = packages_dir / tool_name
        tools_json = pkg_dir / "tools.json"
        installer = packages_dir / "tool-esp_install" / "tools" / "idf_tools.py"

        # Case 1: freshly downloaded stub -- expand and replace the package.
        if tools_json.is_file():
            result = subprocess.run(
                [get_pythonexe_path(), str(installer),
                 "--quiet", "--non-interactive",
                 "--tools-json", str(tools_json), "install"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, check=False,
            )
            if result.returncode != 0:
                tail = (result.stderr or result.stdout or "").strip()[-1000:]
                print("Warning: idf_tools.py install failed for %s: %s"
                      % (tool_name, tail))
                return False

            expanded = core_dir / "tools" / tool_name
            try:
                shutil.copy2(pkg_dir / "package.json", expanded / "package.json")
                shutil.rmtree(pkg_dir)
                # install() writes .piopm and refreshes core's package
                # cache; the version re-pin below then makes the spec
                # resolve straight to this directory (path match).
                ToolPackageManager().install("file://%s" % expanded)
            except OSError as exc:
                print("Warning: failed to install expanded tool %s: %s"
                      % (tool_name, exc))
                return False
            print("Expanded esp tool %s via idf_tools.py" % tool_name)
            platform.packages[tool_name]["version"] = str(pkg_dir)
            return True

        # Case 2: already expanded -- validate the version and prefer local.
        if pkg_dir.is_dir():
            required = platform.packages.get(tool_name, {}).get("package-version")
            installed = None
            try:
                installed = json.loads(
                    (pkg_dir / "package.json").read_text(encoding="utf-8")
                ).get("version")
            except (OSError, json.JSONDecodeError, ValueError):
                pass
            if required and installed != required and not _reinstall:
                print("Version mismatch for %s (%s != %s); reinstalling"
                      % (tool_name, installed, required))
                version_pin = str(platform.packages[tool_name].get("version", ""))
                if not version_pin:
                    return False
                shutil.rmtree(pkg_dir, ignore_errors=True)
                ToolPackageManager().install(version_pin)
                return self._install_esp_tool(
                    platform, tool_name, packages_dir, core_dir, _reinstall=True
                )
            # Normalize dirs left without a .piopm marker (e.g. by an
            # interrupted expansion): core falls back to legacy-spec
            # resolution for those, which is fragile -- re-install from
            # the cached expansion when one is available.
            if not (pkg_dir / ".piopm").exists():
                expanded = core_dir / "tools" / tool_name
                if expanded.is_dir():
                    try:
                        shutil.rmtree(pkg_dir)
                        ToolPackageManager().install("file://%s" % expanded)
                    except OSError as exc:
                        print("Warning: failed to normalize %s: %s"
                              % (tool_name, exc))
            platform.packages[tool_name]["version"] = str(pkg_dir)
            return True

        return False

    @staticmethod
    def _ensure_esptoolpy_runtime_dependencies():
        """Install the pip modules esptool needs into the penv (once per
        process).

        The expanded tool-esptoolpy copy brings no bundled Python deps,
        so install the optional runtime modules it imports: rich_click
        (CLI formatting) and intelhex (image merge / bootloader.bin
        generation).
        """
        global _ESPTOOLPY_DEPS_PREPARED
        if _ESPTOOLPY_DEPS_PREPARED:
            return
        _ESPTOOLPY_DEPS_PREPARED = True

        import subprocess
        from importlib import import_module

        from platformio.proc import get_pythonexe_path

        python_exe = get_pythonexe_path()
        if not python_exe:
            return
        for dep, module in (("rich_click<2", "rich_click"), ("intelhex", "intelhex")):
            try:
                import_module(module)
            except ImportError:
                try:
                    subprocess.run(
                        [python_exe, "-m", "pip", "install", dep,
                         "--disable-pip-version-check", "--no-input"],
                        check=True,
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    print("Warning: failed to install %s for esptoolpy: %s"
                          % (dep, exc))

    @staticmethod
    def _ensure_esp_installer(platform, packages_dir) -> bool:
        """Make sure tool-esp_install (idf_tools.py) is present."""
        installer = packages_dir / "tool-esp_install" / "tools" / "idf_tools.py"
        if installer.is_file():
            return True
        version = platform.packages.get("tool-esp_install", {}).get("version")
        if not version:
            print("Warning: tool-esp_install has no version pin; "
                  "stubs cannot expand")
            return False
        try:
            from platformio.package.manager.tool import ToolPackageManager

            ToolPackageManager().install(version)
        except Exception as exc:  # pylint: disable=broad-except
            print("Warning: failed to install tool-esp_install: %s" % exc)
            return False
        return installer.is_file()
