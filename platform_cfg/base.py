"""Base class for per-family package/debug configuration.

One subclass per architecture family; the class registry lives in
``platform_cfg/__init__.py`` (``FAMILY_CONFIGS``) and ``platform.py``
dispatches through ``get_family_config()``.

``self.platform.packages`` is shared across all families: only touch what
this family needs and never delete another family's packages
(regression tests/test_cross_family_isolation.py).
"""


class FamilyConfig:
    """Per-family hooks; every subclass must override all three."""

    family = None  # "esp" / "nrf" / ... -- set by every subclass

    def __init__(self, platform):
        self.platform = platform  # SeeedstudioPlatform instance

    # ---- hooks (one-to-one with the former module-level functions) ----

    def configure_default_packages(self, variables, targets):
        """Tool selection: flip optional/version flags in platform.packages."""
        raise NotImplementedError

    def add_default_debug_tools(self, board):
        """Register the board's default debug tools in the manifest."""
        raise NotImplementedError

    def configure_debug_session(self, debug_config):
        """Adjust the debug session (GDB server/client options)."""
        raise NotImplementedError
