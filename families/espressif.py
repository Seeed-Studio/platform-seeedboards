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




class UpstreamPlatformProxy:
    """Runtime shim replacing the static forwarding files.

    The upstream pioarduino builders locate their own companion modules
    through env.PioPlatform().get_dir() — the HOST platform directory —
    (spiffsgen.py, penv_setup.py, component_manager.py, boards/<id>.py).
    Handing them this proxy makes get_dir() resolve to the upstream
    package so every such lookup lands inside the upstream copy, while
    everything else (packages, install_tool, debug) forwards to the
    real host platform.
    """

    def __init__(self, host, upstream_dir):
        self._host = host
        self._upstream_dir = upstream_dir

    def get_dir(self):
        return self._upstream_dir

    def __getattr__(self, name):
        return getattr(self._host, name)


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
        self.seed_penv_deps()
        self._prefer_local_esp_tools(platform)

    def _upstream_platform_dir(self):
        from platformio.project.config import ProjectConfig
        platforms_dir = ProjectConfig.get_instance().get("platformio", "platforms_dir")
        return join(platforms_dir, self.upstream_platform)

    def _upstream_matches_lock(self):
        """True when the installed upstream checkout is the locked commit.

        Primary source is the .upstream-lock marker written after a
        successful install: it survives directory copies (offline
        distribution, CI cache extraction), unlike the .git checkout
        which only exists for git-clone installs. Falls back to
        rev-parse for pre-marker installs."""
        upstream_dir = self._upstream_platform_dir()
        locked_sha = self.upstream_version.rsplit("#", 1)[-1]
        try:
            with open(join(upstream_dir, ".upstream-lock"), encoding="utf-8") as fp:
                return fp.read().strip().lower() == locked_sha.lower()
        except OSError:
            pass
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

        Only called when this build requires an ESP32 framework script,
        so a failed install is fatal here (fail fast in configure,
        with the spec and remedy in the message) instead of surfacing
        as a missing builder deep inside SCons.
        """
        if not self.upstream_version:
            return None
        upstream_dir = self._upstream_platform_dir()
        if self._upstream_matches_lock():
            self._write_upstream_lock_marker()
            return upstream_dir

        def _fail(reason):
            sys.stderr.write(
                "Error: this build needs the upstream '%s' platform "
                "package (locked spec: %s) and it is not installed: %s\n"
                "Fix: retry online (auto-installed on first build), or "
                "pre-seed <platforms_dir>/%s from a machine that has it.\n"
                % (self.upstream_platform, self.upstream_version, reason,
                   self.upstream_platform))
            sys.exit(1)

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
            _fail("install failed: %s" % e)

        if not self._upstream_matches_lock():
            _fail("installed version does not match the lock")

        self._write_upstream_lock_marker()
        return upstream_dir

    def _write_upstream_lock_marker(self):
        """Persist the lock marker so copied/deployed checkouts (no
        .git) are recognized without network access."""
        try:
            with open(join(self._upstream_platform_dir(), ".upstream-lock"),
                      "w", encoding="utf-8") as fp:
                fp.write(self.upstream_version.rsplit("#", 1)[-1])
        except OSError as e:
            print("Warning: could not write upstream lock marker: %s" % e)


    def post_configure_packages(self, platform, variables, targets):
        return self._expand_stub_tools_via_upstream(platform)

    def add_default_debug_tools(self, platform, board):
        from platform_cfg import esp_cfg
        return esp_cfg._add_esp_default_debug_tools(platform, board)

    def configure_debug_session(self, platform, debug_config):
        from platform_cfg import esp_cfg
        esp_cfg.configure_esp_debug_session(debug_config)

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
        images, diagnostics). The former local board_build/esp/
        esp_build.py was an official-v6.9.0-era copy of the same file;
        this returns to the upstream mainline. Host-side expectations
        the upstream builder has of its platform object are adapted by
        wrap_platform / setup_python_env below."""
        return join(self._upstream_platform_dir(), "builder", "main.py")

    def wrap_platform(self, platform, env):
        """Hook for the dispatchers: replace env.PioPlatform() with an
        UpstreamPlatformProxy for the duration of the upstream script
        (see that class). Returns the original callable so the caller
        can restore it afterwards."""
        original = env.PioPlatform
        upstream_dir = self._upstream_platform_dir()
        if os.path.isfile(join(upstream_dir, "platform.json")):
            env.PioPlatform = lambda: UpstreamPlatformProxy(original(), upstream_dir)
        return original

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
