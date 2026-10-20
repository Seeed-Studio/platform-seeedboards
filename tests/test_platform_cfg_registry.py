"""Registry behavior: unknown families and unoverridden hooks fail loudly.

platformio.platform.factory is imported before the repo root joins
sys.path so the stdlib platform module is already cached -- the repo's
platform.py must not shadow it for platformio's import chain.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("platformio")
import platformio.platform.factory  # noqa: F401,E402

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))

from platform_cfg import FAMILY_CONFIGS, get_family_config  # noqa: E402
from platform_cfg.base import FamilyConfig  # noqa: E402


def test_every_known_family_is_registered():
    assert sorted(FAMILY_CONFIGS) == [
        "esp",
        "nrf",
        "renesas",
        "rpi",
        "samd",
        "siliconlab",
        "stm32",
    ]


def test_unknown_family_raises_with_valid_list():
    with pytest.raises(ValueError, match="siliconlab"):
        get_family_config("bogus", object())


def test_base_hooks_raise_not_implemented():
    cfg = FamilyConfig(object())
    with pytest.raises(NotImplementedError):
        cfg.configure_default_packages({}, [])
    with pytest.raises(NotImplementedError):
        cfg.add_default_debug_tools(object())
    with pytest.raises(NotImplementedError):
        cfg.configure_debug_session(object())


def test_subclasses_override_all_hooks():
    for family, cls in FAMILY_CONFIGS.items():
        for hook in (
            "configure_default_packages",
            "add_default_debug_tools",
            "configure_debug_session",
        ):
            assert getattr(cls, hook) is not getattr(FamilyConfig, hook), (
                family,
                hook,
            )
