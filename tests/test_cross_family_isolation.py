"""Regression test: cross-family package deletion in cfg modules.

siliconlab_cfg used to unconditionally delete rpi/esp/nrf tool packages
from the shared packages dict, and rpi_cfg popped gccarmnoneeabi -- in a
single process this left later cross-family configuration crashing with
KeyError. Fixed in the cross-family commit of this branch; the test hunk
was omitted from the port at the time (dev had no pytest harness yet) and
is restored here verbatim from the upstream branch.
"""

import pathlib

import pytest

pytest.importorskip("platformio")

from platformio.platform.factory import PlatformFactory  # noqa: E402


def test_siliconlab_then_rpi_esp_nrf_in_one_process():
    """Four families configured through ONE platform instance must not raise."""
    repo = pathlib.Path(__file__).resolve().parents[1]
    platform = PlatformFactory.new(str(repo))
    for board_id, framework in (
        ("seeed-xiao-mg24", "arduino"),
        ("seeed-xiao-rp2040", "arduino"),
        ("seeed-xiao-esp32-c3", "arduino"),
        ("seeed-xiao-mbed-nrf52840", "arduino"),
    ):
        platform.configure_default_packages(
            {"board": board_id, "framework": [framework], "pioframework": [framework]},
            [],
        )
    # All four families configured through one shared instance.


def test_samd_keeps_other_families_uploaders_in_one_process():
    """samd used to delete every type=uploader package from the shared
    packages dict -- its own uploaders (tool-bossac / tool-jlink) carry no
    type field, so esp/renesas/nrf uploaders were collected and deleted
    too. Those packages are optional for samd builds and never install
    there; the deletion only broke later in-process configuration of the
    families that need them (e.g. a multi-env ``pio run``)."""
    repo = pathlib.Path(__file__).resolve().parents[1]
    platform = PlatformFactory.new(str(repo))
    platform.configure_default_packages(
        {"board": "seeed-xiao-samd", "framework": ["arduino"], "pioframework": ["arduino"]},
        [],
    )
    platform.configure_default_packages(
        {"board": "seeed-xiao-esp32-c3", "framework": ["arduino"], "pioframework": ["arduino"]},
        [],
    )
    # esp must still be able to mark its uploader required after samd ran
    assert platform.packages["tool-esptoolpy"]["optional"] is False
