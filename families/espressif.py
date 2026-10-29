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

"""Espressif ESP32 chip family.

Platform-side package matrix and debug-tool behavior are owned here
(inlined from the retired platform_cfg/esp_cfg.py). The ESP32
tool-expansion logic (pioarduino tool-esp_install / idf_tools.py
based expansion and local-package preference) moved here from
platform.py and is owned by this family.

Note: keep this module importable without PlatformIO installed — the
registry (and scripts/ci/verify_board_manifests.py) imports it at module
load; platformio imports stay inside functions.
"""

import os
import subprocess
import sys
from os.path import join
from pathlib import Path

from .base import ChipFamily


def _iter_required_esp_tools(platform):
    return [
        name
        for name, options in platform.packages.items()
        if name != "tool-esp_install"
        and name.startswith(("tool-", "toolchain-"))
        and not options.get("optional", True)
    ]


def _pio():
    from platformio.package.manager.tool import ToolPackageManager
    from platformio.proc import get_pythonexe_path
    from platformio.project.config import ProjectConfig
    return ToolPackageManager, get_pythonexe_path, ProjectConfig


def _get_packages_dir():
    _, _, ProjectConfig = _pio()
    config = ProjectConfig.get_instance()
    return config.get("platformio", "packages_dir")


def _parse_python_deps(source):
    """Extract the python_deps dict literal from penv_setup.py source
    WITHOUT executing it (ast only). Returns {} when absent or not a
    literal dict."""
    import ast
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "python_deps":
                try:
                    return dict(ast.literal_eval(node.value))
                except ValueError:
                    return {}
    return {}


class Esp32Family(ChipFamily):
    family_ids = ("esp32",)

    # Host-side adapters this family mounts for the upstream builder
    # (each depends on an upstream implementation detail — guarded by
    # the anchor tests in tests/test_upstream_anchors.py):
    #   1. UpstreamPlatformProxy   — upstream locates its companion
    #      modules via env.PioPlatform().get_dir()
    #   2. setup_python_env        — upstream main.py calls it on the
    #      host platform object
    #   3. _expand_stub_tools_via_upstream — upstream platform exposes
    #      install_tool()
    #   4. seed_penv_deps          — upstream builder imports the seeded
    #      packages and declares them in penv_setup.python_deps
    upstream_platform = "espressif32"
    upstream_version = (
        "https://github.com/pioarduino/platform-espressif32.git"
        "#b58b4492b841f3518768753443f7d2e9bd1df794"  # 55.03.312
    )
    # configure_esp_default_packages drops these for RISC-V-only MCUs.
    owned_packages = ("toolchain-xtensa-esp-elf", "toolchain-esp32ulp")

    # penv packages seeded from the upstream builder's own dependency
    # list (builder/penv_setup.py -> python_deps). Keys index that dict
    # (pip package names); values are the import names used for the
    # already-installed check. Version constraints come from upstream,
    # so bumping them is not maintained here. Full classification of
    # the upstream list (every upstream key in SEED or EXEMPT, nothing
    # stale on our side) is asserted by tests/test_upstream_anchors.py,
    # so a lock bump with new dependencies turns the PR red.
    PENV_SEED = {
        "littlefs-python": "littlefs",
        "fatfs-ng": "fatfs",
        "pyyaml": "yaml",
        # esptool runtime deps: the stub-expanded tool-esptoolpy copy
        # brings no bundled Python deps, so rich-click (CLI formatting)
        # and intelhex (image merge / bootloader generation) are seeded
        # here — constraints from the upstream list, no local pin.
        "rich-click": "rich_click",
        "intelhex": "intelhex",
    }
    # Upstream deps deliberately not seeded here: platform-management
    # tooling we do not run (pioarduino), Tasmota legacy (zopfli), or
    # transitively present. Both maps together must cover the upstream
    # list exactly (asserted in tests/test_upstream_anchors.py).
    PENV_SEED_EXEMPT = (
        "pioarduino", "rich", "cryptography", "certifi", "ecdsa",
        "bitstring", "reedsolo", "esp-idf-size", "esp-coredump",
        "pyelftools", "zopfli",
    )

    def __init__(self):
        self._penv_seeded = False

    # -- platform side --------------------------------------------------

    def required_packages(self, board):
        """Activate the upstream platform package whenever either ESP32
        framework is requested: both load their builder script from it
        (an espidf-first board like the S31 would otherwise fail on the
        first build)."""
        frameworks = board.get("frameworks", []) if board is not None else []
        if {"arduino", "espidf"} & set(frameworks):
            return {self.upstream_platform}
        return set()

    def configure_default_packages(self, platform, variables, targets):
        # ESP32 package matrix (inlined from the retired
        # platform_cfg/esp_cfg.py; attribution: pioarduino).
        board_config = platform.board_config(variables.get("board"))
        mcu = variables.get("board_build.mcu",
                            board_config.get("build.mcu", "esp32"))

        def _mark_required(package_name):
            if package_name in platform.packages:
                platform.packages[package_name]["optional"] = False

        _mark_required("framework-arduinoespressif32")
        _mark_required("framework-arduinoespressif32-libs")
        _mark_required("esp32-arduino-libs")
        _mark_required("tool-esptoolpy")

        # Make tool-xtensa-esp-elf-gdb and tool-riscv32-esp-elf-gdb required
        for gdb_package in ("tool-xtensa-esp-elf-gdb", "tool-riscv32-esp-elf-gdb"):
            _mark_required(gdb_package)

        # Only "esp32", "esp32s2", "esp32s3" use the toolchain-xtensa-esp-elf
        # toolchain; other MCUs do not, so drop toolchain-xtensa-esp-elf entirely
        if mcu in ("esp32", "esp32s2", "esp32s3"):
            _mark_required("toolchain-xtensa-esp-elf")
        else:
            platform.packages.pop("toolchain-xtensa-esp-elf", None)

        if mcu in ("esp32s2", "esp32s3", "esp32c2", "esp32c3",
                   "esp32c5", "esp32c6", "esp32h2", "esp32p4"):
            if mcu in ("esp32c2", "esp32c3", "esp32c5",
                       "esp32c6", "esp32h2", "esp32p4"):
                platform.packages.pop("toolchain-esp32ulp", None)
            # RISC-V based toolchain for ESP32C3, ESP32C6 ESP32S2, ESP32S3 ULP
            _mark_required("toolchain-riscv32-esp")

        # ROM ELF files: espidf.py references this package via ESP_ROM_ELF_DIR
        # during ESP-IDF builds; leaving it undeclared/uninstalled raises
        # KeyError (pioarduino upstream installs it for all ESP builds)
        _mark_required("tool-esp-rom-elfs")

        # esp32c2 / esp32c61 have no prebuilt Arduino libs; they need the
        # matching skeleton packages
        if mcu == "esp32c2":
            _mark_required("framework-arduino-c2-skeleton-lib")
        if mcu == "esp32c61":
            _mark_required("framework-arduino-c61-skeleton-lib")

        board_name = variables.get("board")
        # The upstream espidf builder drives CMake/Ninja itself; the old
        # local snapshot never activated them (no espidf consumer existed
        # on this platform until now).
        if "espidf" in variables.get("pioframework", []):
            for name in ("tool-cmake", "tool-ninja"):
                if name in platform.packages:
                    platform.packages[name]["optional"] = False
        required = (
            self.required_packages(platform.board_config(board_name))
            if board_name else set()
        )
        # The upstream platform (if needed) installs through
        # PlatformPackageManager below — see _ensure_upstream_platform.
        if self.upstream_platform in required:
            self._ensure_upstream_platform(platform)
        self.seed_penv_deps()
        self._prefer_local_esp_tools(platform)

    def post_configure_packages(self, platform, variables, targets):
        return self._expand_stub_tools_via_upstream(platform)

    def add_default_debug_tools(self, platform, board):
        # ESP32 debug-tool injection (inlined from the retired
        # platform_cfg/esp_cfg.py; attribution: pioarduino).
        if not board.get("upload.protocols", []):
            board.manifest["upload"]["protocols"] = ["esptool", "espota"]
        if not board.get("upload.protocol", ""):
            board.manifest["upload"]["protocol"] = "esptool"

        debug = board.manifest.get("debug", {})
        non_debug_protocols = ["esptool", "espota"]
        supported_debug_tools = [
            "cmsis-dap",
            "esp-prog",
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

        if board.get("build.mcu", "") in ("esp32c3", "esp32c5",
                                          "esp32c6", "esp32s3", "esp32h2"):
            supported_debug_tools.append("esp-builtin")

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

            if link in ("jlink", "cmsis-dap"):
                openocd_interface = link
            elif link in ("esp-prog", "ftdi"):
                openocd_interface = "ftdi/esp32_devkitj_v1"
            elif link == "esp-bridge":
                openocd_interface = "esp_usb_bridge"
            elif link == "esp-builtin":
                openocd_interface = "esp_usb_jtag"
            else:
                openocd_interface = "ftdi/" + link

            server_args = [
                "-s",
                "$PACKAGE_DIR/share/openocd/scripts",
                "-f",
                "interface/%s.cfg" % openocd_interface,
                "-f",
                "%s/%s"
                % (
                    ("target", debug.get("openocd_target"))
                    if "openocd_target" in debug
                    else ("board", debug.get("openocd_board"))
                ),
            ]

            debug["tools"][link] = {
                "server": {
                    "package": "tool-openocd-esp32",
                    "executable": "bin/openocd",
                    "arguments": server_args,
                },
                "init_break": "thb app_main",
                "init_cmds": [
                    "define pio_reset_halt_target",
                    "   monitor reset halt",
                    "   flushregs",
                    "end",
                    "define pio_reset_run_target",
                    "   monitor reset",
                    "end",
                    "target extended-remote $DEBUG_PORT",
                    "$LOAD_CMDS",
                    "pio_reset_halt_target",
                    "$INIT_BREAK",
                ],
                "onboard": link in debug.get("onboard_tools", []),
                "default": link == debug.get("default_tool"),
            }

        board.manifest["debug"] = debug
        return board

    def configure_debug_session(self, platform, debug_config):
        # ESP32 flash-image load commands (inlined from the retired
        # platform_cfg/esp_cfg.py; attribution: pioarduino).
        from platformio.public import to_unix_path

        build_extra_data = debug_config.build_data.get("extra", {})
        flash_images = build_extra_data.get("flash_images", [])

        if "openocd" in (debug_config.server or {}).get("executable", ""):
            debug_config.server["arguments"].extend(
                ["-c", "adapter speed %s" % (debug_config.speed or "5000")]
            )

        ignore_conds = [
            debug_config.load_cmds != ["load"],
            not flash_images,
            not all([os.path.isfile(item["path"]) for item in flash_images]),
        ]

        if any(ignore_conds):
            return

        load_cmds = [
            'monitor program_esp "{{{path}}}" {offset} verify'.format(
                path=to_unix_path(item["path"]), offset=item["offset"]
            )
            for item in flash_images
        ]
        load_cmds.append(
            'monitor program_esp "{%s.bin}" %s verify'
            % (
                to_unix_path(debug_config.build_data["prog_path"][:-4]),
                build_extra_data.get("application_offset", "0x10000"),
            )
        )
        debug_config.load_cmds = load_cmds

    # -- ESP stub-package expansion -------------------------------------

    @staticmethod
    def _prefer_local_esp_tools(platform):
        packages_dir = Path(_get_packages_dir())
        if not packages_dir.exists():
            return

        for tool_name in _iter_required_esp_tools(platform):
            pkg_meta = packages_dir / tool_name / "package.json"
            if pkg_meta.exists() and tool_name in platform.packages:
                platform.packages[tool_name]["version"] = str(packages_dir / tool_name)
                platform.packages[tool_name]["optional"] = False

    def _expand_stub_tools_via_upstream(self, platform):
        """Expand stub packages through the upstream platform's installer
        API — class-level reuse, no local copy of the expansion logic
        (handbook 4.4).

        A stub is a toolchain/uploader zip that PIO installs as
        package.json + tools.json only (the real payload is described in
        tools.json). pioarduino's own Espressif32Platform.install_tool()
        knows how to expand one: it runs tool-esp_install's idf_tools.py,
        REMOVES the stub directory, and installs the expanded payload
        back into the packages dir — which also fixes the stub-shadowing
        gap the old local copy of this logic had. Afterwards our manifest
        entries are linked to the expanded local copies so the core never
        re-downloads the stub. Returns True when our package table
        changed and the platform should re-run its super configuration.
        """
        packages_dir = _get_packages_dir()
        stub_names = [
            name for name in _iter_required_esp_tools(platform)
            if os.path.isfile(join(packages_dir, name, "tools.json"))
        ]
        if not stub_names:
            return False

        upstream_dir = self._upstream_platform_dir()
        if not os.path.isfile(join(upstream_dir, "platform.json")):
            print("Warning: upstream '%s' platform not installed; cannot "
                  "expand stub packages: %s"
                  % (self.upstream_platform, ", ".join(stub_names)))
            return False

        try:
            from platformio.platform.factory import PlatformFactory
            upstream = PlatformFactory.new(upstream_dir)
            for name in stub_names:
                if name not in upstream.packages:
                    print("Warning: upstream platform does not declare "
                          "'%s'; stub left unexpanded" % name)
                    continue
                upstream.install_tool(name)
        except Exception as e:
            print("Warning: upstream stub expansion failed: %s" % e)

        changed = False
        for name in stub_names:
            pkg_dir = join(packages_dir, name)
            expanded = (os.path.isfile(join(pkg_dir, "package.json"))
                        and not os.path.isfile(join(pkg_dir, "tools.json")))
            if expanded and name in platform.packages:
                if platform.packages[name].get("version") != pkg_dir:
                    changed = True
                platform.packages[name]["version"] = pkg_dir
                platform.packages[name]["optional"] = False
        return changed

    # -- builder side ----------------------------------------------------

    def build_script(self, platform, board):
        """The board-level build script is the upstream pioarduino
        builder/main.py itself (env assembly, upload matrix, filesystem
        images, diagnostics). The former local esp build script
        was an official-v6.9.0-era copy of the same file;
        this returns to the upstream mainline. Host-side expectations
        the upstream builder has of its platform object are adapted by
        wrap_platform (base) / setup_python_env below."""
        return join(self._upstream_platform_dir(), "builder", "main.py")

    def setup_python_env(self, platform, env):
        """Host adapter for the upstream builder's
        `platform.setup_python_env(env)` call (its main.py line ~52).

        Returns the already-working pair (penv python, esptool path)
        WITHOUT running the upstream penv machinery: pioarduino's
        setup_penv_minimal assumes it owns the shared PlatformIO penv
        and its uv sync removed core packages (certifi, uvicorn, ...)
        when run here. The penv is PIO core's, not ours to manage.

        The esptool half is resolved by _resolve_esptool: the upstream
        builder execs OBJCOPY directly (no $PYTHONEXE prefix), so it
        must be a real executable path — never the bare program name
        (PIO 6.2's where_is_program returns it when nothing is found)
        nor the package's esptool.py (unpacked without the exec bit on
        Linux)."""
        penv_python = getattr(platform, "_penv_python", None)
        esptool_path = getattr(platform, "_esptool_path", None)
        if not penv_python:
            from platformio.proc import get_pythonexe_path
            penv_python = get_pythonexe_path()
        if not esptool_path:
            esptool_path = self._resolve_esptool(penv_python)
        platform._penv_python = penv_python
        platform._esptool_path = esptool_path
        if penv_python:
            env.Replace(PYTHONEXE=penv_python)
        return penv_python, esptool_path

    @staticmethod
    def _is_usable_executable(path):
        """True only for an existing executable FILE. Guards against
        PIO 6.2's where_is_program() returning the bare program name
        when lookup fails, and against names that resolve to a
        directory (the tool-esptoolpy package root is prepended to
        $PATH for uploader packages and contains the esptool *package
        directory*)."""
        return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)

    def _resolve_esptool(self, penv_python):
        """Pick the esptool executable handed to the upstream builder.

        Preference order:
        1. an esptool entry point already on $PATH (e.g. installed in
           the penv) — used as-is;
        2. a generated launcher that runs tool-esptoolpy's esptool.py
           under the penv python (whose deps seed_penv_deps provides).

        Both keep the upstream contract of a single exec'able path;
        returning "" only when neither can be produced."""
        from platformio.proc import where_is_program
        candidate = where_is_program("esptool")
        if self._is_usable_executable(candidate):
            return candidate
        esptool_py = join(_get_packages_dir(), "tool-esptoolpy", "esptool.py")
        if not os.path.isfile(esptool_py) or not penv_python:
            return ""
        return self._write_esptool_wrapper(esptool_py, penv_python)

    @staticmethod
    def _esptool_wrapper_path():
        from platformio.project.config import ProjectConfig
        core_dir = ProjectConfig.get_instance().get("platformio", "core_dir")
        wrapper = "esptool.cmd" if sys.platform == "win32" else "esptool"
        return join(core_dir, ".cache", "esptool-wrapper", wrapper)

    def _write_esptool_wrapper(self, esptool_py, penv_python):
        """(Re)create the esptool launcher under the core cache dir.

        Rewritten whenever the embedded paths change, so package or
        penv moves invalidate it automatically."""
        if sys.platform == "win32":
            body = '@"%s" "%s" %%*\r\n' % (penv_python, esptool_py)
        else:
            body = '#!/bin/sh\nexec "%s" "%s" "$@"\n' % (penv_python, esptool_py)
        wrapper = self._esptool_wrapper_path()
        try:
            os.makedirs(os.path.dirname(wrapper), exist_ok=True)
            try:
                with open(wrapper, encoding="utf-8", errors="replace") as fp:
                    if fp.read() == body:
                        return wrapper
            except OSError:
                pass  # not created yet — write it below
            with open(wrapper, "w", encoding="utf-8", newline="") as fp:
                fp.write(body)
            os.chmod(wrapper, 0o755)
        except OSError as e:
            print("Warning: could not write esptool wrapper %s: %s"
                  % (wrapper, e))
            return ""
        return wrapper

    def seed_penv_deps(self):
        """Idempotently pre-seed the penv with the build-time Python
        packages the upstream builder imports (see PENV_SEED). Version
        constraints are read from the upstream's own python_deps list —
        this never runs the upstream penv machinery (see
        setup_python_env), it only consumes its dependency declaration.
        """
        if self._penv_seeded:
            return
        self._penv_seeded = True

        upstream_deps = self._upstream_python_deps()
        if upstream_deps is None:
            return

        _, get_pythonexe_path, _ = _pio()
        python_exe = get_pythonexe_path()
        if not python_exe:
            return
        for pip_name, module in self.PENV_SEED.items():
            # Probe the PENV, not this PIO process: the host
            # interpreter may already have the module (preseeded on CI,
            # or a plain `pip install platformio` env) while the penv
            # that actually runs the upstream builder's tools does not.
            if self._penv_can_import(python_exe, module):
                continue
            constraint = upstream_deps.get(pip_name, "")
            try:
                subprocess.run(
                    [python_exe, "-m", "pip", "install",
                     pip_name + constraint,
                     "--disable-pip-version-check", "--no-input"],
                    check=True)
            except Exception as e:
                print("Warning: failed to install %s for upstream "
                      "builder: %s" % (pip_name, e))

    @staticmethod
    def _penv_can_import(python_exe, module):
        try:
            result = subprocess.run(
                [python_exe, "-c", "import %s" % module],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError:
            return False
        return result.returncode == 0

    def _upstream_python_deps(self):
        """Read the installed upstream python_deps declaration (ast
        only, never executed — see _parse_python_deps)."""
        try:
            with open(join(self._upstream_platform_dir(),
                           "builder", "penv_setup.py"),
                      encoding="utf-8") as fp:
                return _parse_python_deps(fp.read()) or None
        except OSError:
            return None

        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "python_deps":
                    try:
                        return dict(ast.literal_eval(node.value))
                    except ValueError:
                        print("Warning: upstream python_deps is no longer "
                              "a literal dict; penv seeding is disabled")
                        return None
        print("Warning: upstream python_deps assignment not found; "
              "penv seeding is disabled")
        return None

    def framework_script(self, platform, framework, board):
        """Both ESP32 frameworks load upstream pioarduino scripts
        (platform espressif32, locked by upstream_version, installed into
        the platforms dir by _ensure_upstream_platform) — no local
        copies."""
        if framework not in ("arduino", "espidf"):
            return None
        upstream_dir = self._upstream_platform_dir()
        script = join(upstream_dir, "builder", "frameworks", framework + ".py")
        if not os.path.isfile(script):
            sys.stderr.write(
                "Error: ESP32 %s builds require the upstream '%s' "
                "platform package (locked by upstream_version); expected "
                "its builder at %s\n"
                % (framework, self.upstream_platform, script))
            sys.exit(1)
        return script
