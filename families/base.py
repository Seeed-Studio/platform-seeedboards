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

"""ChipFamily abstract base, automatic registry, and board routing.

Contract:
- Every boards/<id>.json MUST declare ``build.chip_family`` whose value
  matches one of the registered families' ``family_ids``. There is
  intentionally no board-id substring fallback: an unknown or missing value
  fails loudly with the list of valid values and the file to fix.
- Registering a family = adding one module under ``families/`` plus one
  import line in ``families/__init__.py``; ``__init_subclass__`` registers
  the class at import time.
- The packages dict on the platform instance is global across families.
  A family must never drop another family's packages; use ``drop_package``
  which asserts ownership via ``owned_packages``.

Upstream loading (families that declare ``upstream_platform``):
- The upstream platform repo is declared as a locked-version package in
  platform.json and installed under the PlatformIO packages dir.
- ``framework_script()`` returns the absolute path of a builder script
  inside that package; the wrapper SConscripts it, then applies the hooks
  from ``get_build_hooks()``. The platform repo keeps no local copy of
  upstream scripts.
"""

import sys
from os.path import abspath, dirname, isdir, isfile, join


class UpstreamPlatformProxy:
    """Presents an upstream platform package as the PioPlatform object.

    Upstream builders locate companion modules and assets via
    env.PioPlatform().get_dir() — the HOST platform directory.
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


class FamilyResolutionError(ValueError):
    """A board manifest lacks a usable ``build.chip_family`` value."""


class ChipFamily:
    """Base class for per-chip-family routing and behavior.

    Families are stateless singletons except for deliberately kept
    preparation flags (see ``families/espressif.py``), so the registry
    caches one instance per class.
    """

    # Override in subclasses; the first id is the canonical one used in
    # boards/*.json "build.chip_family".
    family_ids = ()

    # Package name of the upstream platform this family loads builder
    # scripts from (None = all builder scripts are local).
    upstream_platform = None

    # Packages this family owns and may drop from the shared packages dict.
    owned_packages = ()

    _registry = {}  # family id -> class
    _instances = {}  # class -> singleton instance

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        ids = tuple(getattr(cls, "family_ids", ()) or ())
        if not ids:
            # Intermediate base classes (no ids) are not registrable.
            return
        for family_id in ids:
            existing = ChipFamily._registry.get(family_id)
            if existing is not None and existing is not cls:
                raise RuntimeError(
                    "duplicate family id '%s' registered by %s and %s"
                    % (family_id, existing.__name__, cls.__name__)
                )
            ChipFamily._registry[family_id] = cls

    # ------------------------------------------------------------------
    # Registry lookups
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, family_id):
        """Return the family instance for a canonical or alias id."""
        try:
            family_cls = cls._registry[family_id]
        except KeyError:
            valid = ", ".join(sorted(cls._registry))
            raise FamilyResolutionError(
                "unknown build.chip_family '%s'; valid values: %s"
                % (family_id, valid)
            )
        if family_cls not in cls._instances:
            cls._instances[family_cls] = family_cls()
        return cls._instances[family_cls]

    @classmethod
    def resolve(cls, board_config, board_id=""):
        """Resolve the family from a board manifest (PlatformBoardConfig
        or a mapping). Raises FamilyResolutionError with an actionable
        message when ``build.chip_family`` is missing or unknown.
        """
        family_id = board_config.get("build.chip_family", "")
        if not family_id:
            raise FamilyResolutionError(
                "board '%s' has no build.chip_family in boards/%s.json; "
                "add it to the \"build\" section (e.g. \"chip_family\": "
                "\"nrf\"). Valid values: %s"
                % (board_id, board_id, ", ".join(sorted(cls._registry)))
            )
        return cls.get(family_id)

    @classmethod
    def registered_ids(cls):
        return tuple(sorted(cls._registry))

    # ------------------------------------------------------------------
    # Handbook interface (defaults; families override as they adopt the
    # declarative contract)
    # ------------------------------------------------------------------

    def required_packages(self, board):
        """Packages this family needs for the board (documentation and
        validation aid; actual activation happens in
        configure_default_packages today)."""
        return set()

    def get_build_hooks(self, framework):
        """Hooks (callables taking (env, board)) applied after the
        framework script has run."""
        return []

    # ------------------------------------------------------------------
    # Platform-side hooks (each family owns these; inlined from the
    # retired platform_cfg/* modules)
    # ------------------------------------------------------------------

    def configure_default_packages(self, platform, variables, targets):
        pass

    def add_default_debug_tools(self, platform, board):
        return board

    def configure_debug_session(self, platform, debug_config):
        pass

    def post_configure_packages(self, platform, variables, targets):
        """Runs after PlatformBase.configure_default_packages; return True
        to have the platform re-run its super configuration."""
        return False

    # ------------------------------------------------------------------
    # Builder-side script mapping (SCons-time)
    # ------------------------------------------------------------------

    def build_script(self, platform, board):
        """Absolute path of the board-level build script
        (builder/families/<family>/...), or None to skip."""
        return None

    def framework_script(self, platform, framework, board):
        """Absolute path of the framework script to SConscript (an
        upstream-package script or a local one), or None."""
        return None

    def zephyr_pioplatform(self):
        """PlatformIO platform name the Zephyr build should present
        (PIOPLATFORM override), or None to keep this platform's name."""
        return None

    def host_dir(self):
        """This platform repo's root, derived from this file's location.

        Use instead of env.PioPlatform().get_dir() in SCons-time code:
        families that load an upstream builder run with PioPlatform
        wrapped (get_dir() = the upstream package), and any host path
        built from it would silently target the upstream copy."""
        return dirname(dirname(abspath(__file__)))

    # ------------------------------------------------------------------
    # Upstream platform loading (families that declare upstream_platform)
    # ------------------------------------------------------------------

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
        if not isdir(join(upstream_dir, ".git")):
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
        """Install the locked upstream platform via PlatformPackageManager.

        Upstream platform repos ship a platform.json manifest (no
        package.json), so the regular tool-package channel refuses them;
        PlatformPackageManager accepts platform.json and installs into
        the platforms dir. Dependencies are skipped — this platform owns
        its package set, never the upstream one. The locked spec lives
        in upstream_version (kept here, not in platform.json's packages:
        it is a source reference, not a core-installable package). When
        the lock moves, a stale install is uninstalled first so the
        upgrade is maintainer-driven but automatic in effect.

        Only call this when a build actually loads builder scripts from
        the upstream platform, so a failed install is fatal in
        configure (fail fast, with the spec and remedy in the message)
        instead of surfacing as a missing builder deep inside SCons.
        """
        if not self.upstream_platform or not self.upstream_version:
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
            if isdir(join(upstream_dir, ".git")):
                # skip_dependencies: the upstream platform's uninstall
                # would otherwise remove shared packages that this
                # platform installed itself.
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

    def wrap_platform(self, platform, env):
        """Hook for the dispatchers: replace env.PioPlatform() with an
        UpstreamPlatformProxy for the duration of the upstream script
        (see that class). Returns the original callable so the caller
        can restore it afterwards; None without an upstream platform.
        The proxy is only mounted when the upstream checkout actually
        carries a platform.json (i.e. _ensure_upstream_platform ran)."""
        if not self.upstream_platform:
            return None
        original = env.PioPlatform
        upstream_dir = self._upstream_platform_dir()
        if isfile(join(upstream_dir, "platform.json")):
            env.PioPlatform = lambda: UpstreamPlatformProxy(original(), upstream_dir)
        return original

    # ------------------------------------------------------------------
    # Shared guarded helpers
    # ------------------------------------------------------------------

    def drop_package(self, platform, name):
        """Remove a package from the shared packages dict, asserting this
        family owns it (guards against deleting another family's
        packages)."""
        if name not in self.owned_packages:
            raise ValueError(
                "family %s does not own package '%s'; refusing to drop it"
                % (type(self).__name__, name)
            )
        platform.packages.pop(name, None)


def resolve_board_family(board_config, board_id=""):
    """Resolve wrapper used from platform.py and SCons builders: prints
    the actionable error and exits instead of raising."""
    try:
        return ChipFamily.resolve(board_config, board_id)
    except FamilyResolutionError as exc:
        sys.stderr.write("Error: %s\n" % exc)
        sys.exit(1)
