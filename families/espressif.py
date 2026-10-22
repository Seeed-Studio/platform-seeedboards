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

Platform-side package/debug behavior delegates to platform_cfg.esp_cfg.
The ESP32 tool-expansion logic (pioarduino tool-esp_install / idf_tools.py
based expansion and local-package preference) moved here from platform.py
and is owned by this family.

Note: keep this module importable without PlatformIO installed — the
registry (and scripts/ci/verify_board_manifests.py) imports it at module
load; platformio and platform_cfg imports stay inside functions.
"""

import os
import subprocess
import sys
from importlib import import_module
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


def _get_core_dir():
    _, _, ProjectConfig = _pio()
    config = ProjectConfig.get_instance()
    return config.get("platformio", "core_dir")


def _ensure_esp_installer(platform, packages_dir):
    installer = packages_dir / "tool-esp_install" / "tools" / "idf_tools.py"
    if installer.exists():
        return

    package_data = platform.packages.get("tool-esp_install", {})
    version = package_data.get("version")
    if not version:
        return

    ToolPackageManager, _, _ = _pio()
    try:
        ToolPackageManager().install(version)
    except Exception as e:
        print("Warning: failed to install tool-esp_install: %s" % e)


def _expand_and_link_esp_tool(platform, tool_name, packages_dir, core_dir):
    ToolPackageManager, get_pythonexe_path, _ = _pio()
    pkg_dir = packages_dir / tool_name
    tools_json = pkg_dir / "tools.json"
    if not tools_json.exists():
        return False

    installer = packages_dir / "tool-esp_install" / "tools" / "idf_tools.py"
    core_tool_dir = core_dir / "tools" / tool_name

    if not (core_tool_dir / "package.json").exists():
        if not installer.exists():
            print("Warning: idf_tools.py not found, cannot expand %s" % tool_name)
            return False

        cmd = [
            get_pythonexe_path(),
            str(installer),
            "--quiet",
            "--non-interactive",
            "--tools-json",
            str(tools_json),
            "install",
        ]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip()[-1000:]
            print("Warning: failed to expand %s via idf_tools.py: %s" % (tool_name, tail))
            return False

    if not (core_tool_dir / "package.json").exists():
        return False

    changed = False
    try:
        pkg_meta = pkg_dir / "package.json"
        if not pkg_meta.exists():
            ToolPackageManager().install("file://%s" % core_tool_dir)
            changed = True

        if tool_name in platform.packages:
            linked_version = str(packages_dir / tool_name)
            if platform.packages[tool_name].get("version") != linked_version:
                changed = True
            platform.packages[tool_name]["version"] = linked_version
            platform.packages[tool_name]["optional"] = False
    except Exception as e:
        print("Warning: failed to link expanded tool %s: %s" % (tool_name, e))
        return False

    return changed


class Esp32Family(ChipFamily):
    family_ids = ("esp32",)
    # Upstream pioarduino platform: installed from this locked spec into
    # the platforms dir (see _ensure_upstream_platform), and its
    # builder/frameworks/arduino.py is SConscript-dynamically loaded —
    # no local copy of the script. Bumping this = maintainer-driven
    # upstream upgrade + regression.
    upstream_platform = "espressif32"
    upstream_version = (
        "https://github.com/pioarduino/platform-espressif32.git"
        "#b58b4492b841f3518768753443f7d2e9bd1df794"  # 55.03.312
    )
    # configure_esp_default_packages drops these for RISC-V-only MCUs.
    owned_packages = ("toolchain-xtensa-esp-elf", "toolchain-esp32ulp")

    def __init__(self):
        self._tools_prepared = False
        self._python_deps_prepared = False

    # -- platform side --------------------------------------------------

    def required_packages(self, board):
        """Activate the upstream platform package whenever the Arduino
        framework is requested: its builder script is the entry point."""
        frameworks = board.get("frameworks", []) if board is not None else []
        packages = set()
        if "arduino" in frameworks:
            packages.add(self.upstream_platform)
        return packages

    def configure_default_packages(self, platform, variables, targets):
        from platform_cfg import esp_cfg
        esp_cfg.configure_esp_default_packages(platform, variables, targets)
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
        self._prefer_local_esp_tools(platform)
        self._ensure_esptoolpy_runtime_dependencies()

    def _upstream_platform_dir(self):
        from platformio.project.config import ProjectConfig
        platforms_dir = ProjectConfig.get_instance().get("platformio", "platforms_dir")
        return join(platforms_dir, self.upstream_platform)

    def _upstream_matches_lock(self):
        """True when the installed upstream checkout is the locked commit.
        The installed manifest's version is the upstream's own tag string
        (e.g. '55.03.312'), which says nothing about the exact commit, so
        compare against the VCS checkout instead."""
        upstream_dir = self._upstream_platform_dir()
        if not os.path.isdir(join(upstream_dir, ".git")):
            return False
        import subprocess
        try:
            result = subprocess.run(
                ["git", "-C", upstream_dir, "rev-parse", "HEAD"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return False
        locked_sha = self.upstream_version.rsplit("#", 1)[-1]
        return result.stdout.strip().lower().startswith(locked_sha[:7].lower())

    def _ensure_upstream_platform(self, platform):
        """Install the locked upstream pioarduino platform via
        PlatformPackageManager.

        pioarduino ships a platform.json manifest (no package.json), so
        the regular tool-package channel refuses it;
        PlatformPackageManager accepts platform.json and installs into
        the platforms dir. Dependencies are skipped — this platform owns
        its package set. The locked spec lives in upstream_version
        (kept here, not in platform.json's packages: it is a source
        reference, not a core-installable package). When the lock moves,
        a stale install is uninstalled first so the upgrade is
        maintainer-driven but automatic in effect (handbook 4.7).
        """
        if not self.upstream_version:
            return None
        upstream_dir = self._upstream_platform_dir()
        if self._upstream_matches_lock():
            return upstream_dir
        try:
            from platformio.package.manager.platform import PlatformPackageManager
            pm = PlatformPackageManager()
            if os.path.isdir(join(upstream_dir, ".git")):
                # skip_dependencies: pioarduino's uninstall would otherwise
                # remove shared packages (framework-espidf, toolchains)
                # that this platform installed itself.
                pm.uninstall(self.upstream_platform, skip_dependencies=True)
            pm.install(self.upstream_version, skip_dependencies=True)
        except Exception as e:
            print("Warning: failed to install upstream '%s' platform: %s"
                  % (self.upstream_platform, e))
            return None
        if self._upstream_matches_lock():
            return upstream_dir
        return None

    def post_configure_packages(self, platform, variables, targets):
        return self._prepare_esp_tools(platform)

    def add_default_debug_tools(self, platform, board):
        from platform_cfg import esp_cfg
        return esp_cfg._add_esp_default_debug_tools(platform, board)

    def configure_debug_session(self, platform, debug_config):
        from platform_cfg import esp_cfg
        esp_cfg.configure_esp_debug_session(debug_config)

    # -- ESP tool expansion (moved from platform.py) --------------------

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

    def _prepare_esp_tools(self, platform):
        if self._tools_prepared:
            return False

        packages_dir = Path(_get_packages_dir())
        core_dir = Path(_get_core_dir())
        if not packages_dir.exists() or not core_dir.exists():
            return False

        _ensure_esp_installer(platform, packages_dir)

        changed = False
        for tool_name in _iter_required_esp_tools(platform):
            if _expand_and_link_esp_tool(platform, tool_name, packages_dir, core_dir):
                changed = True

        self._tools_prepared = True
        return changed

    def _ensure_esptoolpy_runtime_dependencies(self):
        if self._python_deps_prepared:
            return

        self._python_deps_prepared = True

        _, get_pythonexe_path, _ = _pio()
        python_exe = get_pythonexe_path()
        if not python_exe:
            return
        # esptool runs from the $PYTHONEXE (penv) python with the
        # tool-esptoolpy dir on PYTHONPATH. That tool copy is expanded by
        # idf_tools.py and brings no bundled Python deps, so install the
        # optional runtime modules it imports: rich_click (CLI formatting)
        # and intelhex (image merge / bootloader.bin generation).
        for dep, module in (("rich_click<2", "rich_click"),
                            ("intelhex", "intelhex")):
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
                except Exception as e:
                    print("Warning: failed to install %s for esptoolpy: %s" % (dep, e))

    # -- builder side ----------------------------------------------------

    def build_script(self, platform, board):
        return join(platform.get_dir(), "builder", "board_build", "esp", "esp_build.py")

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
