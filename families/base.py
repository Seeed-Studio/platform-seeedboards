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

    def build_flags(self, board):
        return []

    def upload_protocol(self, board):
        return board.get("upload.protocol", "")

    def get_build_hooks(self, framework):
        """Hooks (callables taking (env, board)) applied after the
        framework script has run."""
        return []

    def configure_env(self, env, board):
        return None

    # ------------------------------------------------------------------
    # Platform-side hooks (current behavior delegates to platform_cfg/*)
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
        (builder/board_build/<family>/...), or None to skip."""
        return None

    def framework_script(self, platform, framework, board):
        """Absolute path of the framework script to SConscript (an
        upstream-package script or a local one), or None."""
        return None

    def zephyr_pioplatform(self):
        """PlatformIO platform name the Zephyr build should present
        (PIOPLATFORM override), or None to keep this platform's name."""
        return None

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
