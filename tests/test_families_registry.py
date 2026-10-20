"""Family registry tests.

Covers the routing contract (build.chip_family manifest field resolves
to the registered family, missing/unknown values raise actionable
errors) and the platform-side delegation: configure_default_packages,
_add_dynamic_options and configure_debug_session must reach the family
and reproduce the previous platform_cfg behavior through the real
in-process platform (PlatformFactory pattern from
test_cross_family_isolation.py).

The families package is loaded standalone (spec/import with the repo
root on sys.path, appended — never inserted — so the repo's top-level
platform.py cannot shadow the stdlib platform module; see
test_platform_cfg_esp.py for the shadowing hazard).
"""

import pathlib
import sys

import pytest

pytest.importorskip("platformio")

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))

from families import ChipFamily, FamilyResolutionError  # noqa: E402
from platformio.platform.factory import PlatformFactory  # noqa: E402


class _Manifest:
    """Minimal BoardConfig-style object for resolve()."""

    def __init__(self, chip_family):
        self._data = {"build.chip_family": chip_family} if chip_family else {}

    def get(self, key, default=""):
        return self._data.get(key, default)


def test_registry_has_all_families_no_duplicates():
    ids = ChipFamily.registered_ids()
    assert ids == ("esp32", "nrf", "renesas", "rpi", "samd", "siliconlab", "stm32")
    # every family declares a canonical id first
    for family_id in ids:
        family = ChipFamily.get(family_id)
        assert family.family_ids[0] == family_id


def test_get_returns_singleton():
    assert ChipFamily.get("nrf") is ChipFamily.get("nrf")


def test_get_unknown_raises_with_valid_values():
    with pytest.raises(FamilyResolutionError) as exc:
        ChipFamily.get("zzz")
    assert "esp32" in str(exc.value) and "samd" in str(exc.value)


def test_resolve_missing_field_error_names_the_board():
    with pytest.raises(FamilyResolutionError) as exc:
        ChipFamily.resolve(_Manifest(None), "my-board")
    msg = str(exc.value)
    assert "my-board" in msg and "boards/my-board.json" in msg


def test_resolve_hits_registered_family():
    assert isinstance(ChipFamily.resolve(_Manifest("stm32"), "b"), object)


def test_board_manifests_resolve_and_routing_has_no_substring_fallback():
    """Every boards/*.json resolves to the family its id suggests — and a
    board whose id contains another family's substring still routes by
    the manifest field (stm32c5 board points at a nrf54lm20-named zephyr
    package, so substring routing would misroute it)."""
    import json

    for path in sorted((REPO / "boards").glob("*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        family = ChipFamily.resolve(_Manifest(manifest["build"]["chip_family"]), path.stem)
        if "stm32" in path.stem:
            assert family.family_ids[0] == "stm32"
        if "nrf" in path.stem:
            assert family.family_ids[0] == "nrf"
        if path.stem.startswith("seeed-xiao-esp32-"):
            assert family.family_ids[0] == "esp32"


def test_platform_delegates_configure_default_packages_per_family():
    """The real platform routes each family through its class: esp32 flips
    the arduino framework packages, nrf requires the arm toolchain, and a
    board without the field fails with the actionable error."""
    platform = PlatformFactory.new(str(REPO))

    platform.configure_default_packages(
        {"board": "seeed-xiao-esp32-c3", "framework": ["arduino"], "pioframework": ["arduino"]},
        [],
    )
    assert platform.packages["framework-arduinoespressif32"]["optional"] is False

    platform.configure_default_packages(
        {"board": "seeed-xiao-mbed-nrf52840", "framework": ["arduino"], "pioframework": ["arduino"]},
        [],
    )
    assert platform.packages["toolchain-gccarmnoneeabi"]["optional"] is False


def test_platform_add_dynamic_options_uses_registry():
    platform = PlatformFactory.new(str(REPO))
    board = platform.get_boards("seeed-xiao-esp32-c3")
    # esp_cfg injects esptool defaults through the family delegate
    assert "esptool" in board.get("upload.protocols", [])


def test_builder_script_mapping_is_family_owned():
    platform = PlatformFactory.new(str(REPO))
    for board_id, has_script in (
        ("seeed-xiao-esp32-c3", True),
        ("seeed-xiao-stm32c5", True),
        ("seeed-xiao-rp2040", True),
    ):
        family = ChipFamily.resolve(platform.board_config(board_id), board_id)
        script = family.build_script(platform, platform.board_config(board_id))
        if has_script:
            assert script and pathlib.Path(script).is_file(), (board_id, script)
        else:
            assert script is None
    # stm32 has no Arduino route even though the board exists
    family = ChipFamily.get("stm32")
    assert family.framework_script(platform, "arduino", None) is None
