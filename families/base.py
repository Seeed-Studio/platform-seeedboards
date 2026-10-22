"""ChipFamily abstract base class and auto-registration registry.

Every family module subclasses ChipFamily and declares family_ids; the
subclass hook registers it into ChipFamily._registry automatically.
families/__init__.py imports each family module (one line per family)
to trigger registration -- that import is the only side-effecting one.
See docs/decisions/0001-chipfamily-registry.md for the design contract.
"""

from abc import ABC, abstractmethod
from typing import Optional


class ChipFamily(ABC):
    """One MCU family line (e.g. SAMD21/SAMD51, ESP32, nRF54).

    The manifest's build.chip_family value selects a family through
    ChipFamily.get() -- the only routing path; platform.py and
    builder/main.py carry no chip-name literals.

    Interface contract (ADR-0001):
        required_packages      names (+ optional version overrides) to
                               activate; the single-slot rule (ADR-0002)
                               applies -- overrides narrow, never widen
        build_flags           per-board compile flags
        upload_protocol       default upload protocol name (the family's
                              upload ACTION construction lives in its
                              build script / hooks, not here)
        inject_debug_tools    synthesize debug.tools entries on the board
                              manifest (every upstream platform does this;
                              ~80 lines per family, not optional in practice)
        configure_debug_session  tweak the debug server config before launch
        build_script          path to the family build entry the core delegates to
        get_build_hooks       optional pre/post/middleware SCons hooks
        configure_env         optional env overrides at build entry
    """

    family_ids: tuple = ()

    _registry: dict = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Note: __abstractmethods__ is not yet populated when this hook
        # runs, so abstractness cannot be detected here. Intermediate
        # bases skip registration by declaring family_ids = (); a
        # concrete family that forgets family_ids is caught by the
        # verify_boards gate after class creation completes.
        ids = getattr(cls, "family_ids", ())
        registry = cls._registry
        for family_id in ids:
            existing = registry.get(family_id)
            if existing is not None and existing is not cls:
                raise TypeError(
                    "family_id %r already registered by %s (conflicts with %s)"
                    % (family_id, existing.__name__, cls.__name__)
                )
            registry[family_id] = cls

    @classmethod
    def get(cls, family_id: Optional[str]) -> Optional["ChipFamily"]:
        """Resolve a family by one of its family_ids.

        Returns None when family_id is None or empty (no family
        handling); raises KeyError with the known vocabulary when the
        value is present but unknown -- callers decide which is which.
        """
        if not family_id:
            return None
        klass = cls._registry.get(family_id)
        if klass is None:
            raise KeyError(
                "unknown chip family %r (manifest build.chip_family); "
                "known: %s" % (family_id, ", ".join(sorted(cls._registry)))
            )
        return klass()

    @classmethod
    def known_family_ids(cls) -> tuple:
        return tuple(sorted(cls._registry))

    # -- interface ------------------------------------------------------------

    @abstractmethod
    def required_packages(self, board, variables=None) -> "dict[str, Optional[str]]":
        """Packages to activate for this board: name -> version override
        (None = platform.json pin as-is). Returns a dict, not a set, so
        families can narrow versions per ADR-0002 with evidence in the
        family module's comments. `variables` carries the project options
        (board_build.* overrides, pioframework) for families whose package
        set depends on them; it may be None in unit-test contexts."""

    @abstractmethod
    def build_flags(self, board) -> list:
        """Per-board build flags (CCFLAGS/defines derived from the
        manifest; board facts come from the manifest, never literals
        here)."""

    @abstractmethod
    def upload_protocol(self, board) -> str:
        """Default upload protocol for this board (e.g. 'sam-ba')."""

    @abstractmethod
    def inject_debug_tools(self, board) -> None:
        """Populate board.manifest['debug']['tools'] for the probes this
        family supports (cmsis-dap/jlink/blackmagic/...), reusing the
        board manifest's debug fields; assert-with-message on missing
        required fields."""

    @abstractmethod
    def configure_debug_session(self, debug_config) -> None:
        """Adjust the debug server configuration before launch (adapter
        speed and friends)."""

    def get_build_hooks(self) -> list:
        """Optional SCons hooks: [{'type': 'pre'|'post'|'middleware',
        'target': ..., 'callback': ...}, ...]. Empty by default."""
        return []

    def configure_env(self, env, board) -> None:
        """Optional env overrides at build entry (upload flags, builders).
        Default: no-op."""
        return None

    def post_activate_packages(self, platform) -> bool:
        """Called AFTER super().configure_default_packages() (packages
        downloaded, stubs present) but before the second super() pass.
        For family-specific package preparation -- the ESP stub-package
        expansion lives here. Return True if any packages were modified
        (triggers a re-resolve via a second super() call). Default: no-op."""
        return False

    @abstractmethod
    def build_script(self, env, board) -> str:
        """Path (relative to builder/) of the family build script this
        board should be SConscript'ed into -- either adapted upstream
        code (family-owned) or a package-shipped script path. The core
        never decides this; the family does (ADR-0004 reuse ladder)."""

    def arduino_script(self, env, board) -> str:
        """Path (relative to the framework script's directory) of the
        family's Arduino build script; delegated from the framework
        entry (builder/frameworks/arduino.py). Families without Arduino
        support keep the default, which fails loudly if routed to."""
        raise NotImplementedError(
            "%s does not support the arduino framework"
            % type(self).__name__
        )

    def zephyr_script(self, env, board) -> str:
        """Path (relative to the framework script's directory) of the
        family's Zephyr build script; delegated from the framework entry
        (builder/frameworks/zephyr.py). Families without Zephyr support
        keep the default, which fails loudly if routed to."""
        raise NotImplementedError(
            "%s does not support the zephyr framework"
            % type(self).__name__
        )
