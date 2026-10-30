"""Unit tests for the SiliconlabFamily package matrix and debug tools.

The behavior was inlined from the retired platform_cfg/siliconlab_cfg.py
(the dead openocd_path dict at its top died with the inline); the
family class now owns it. Local-keep family: no upstream anchors —
these unit tests are the regression net (guide execution card 5).
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("platformio")

from platformio.platform.board import PlatformBoardConfig  # noqa: E402
from platformio.platform.factory import PlatformFactory  # noqa: E402
from platformio import util  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))

from families import ChipFamily  # noqa: E402


@pytest.fixture(scope="module")
def siliconlab_family():
    return ChipFamily.get("siliconlab")


@pytest.fixture(scope="module")
def configured_packages():
    platform = PlatformFactory.new(str(REPO))
    platform.configure_default_packages(
        {"board": "seeed-xiao-mg24",
         "framework": ["arduino"], "pioframework": ["arduino"]},
        [],
    )
    return platform.packages


def board_config(board_id):
    return PlatformBoardConfig(str(REPO / "boards" / f"{board_id}.json"))


class TestPackageMatrix:
    def test_toolchain_pinned_and_mandatory(self, configured_packages):
        toolchain = configured_packages["toolchain-gccarmnoneeabi"]
        assert toolchain["version"] == "1.120301.0"
        assert toolchain["optional"] is False

    def test_framework_and_openocd_mandatory(self, configured_packages):
        assert configured_packages["framework-arduino-silabs"]["optional"] is False
        assert configured_packages["tool-openocd"]["optional"] is False

    def test_openocd_redirected_to_seeed_build(self, configured_packages):
        """The Seeed for-silicon openocd (efm32s2 flash loader) replaces
        the registry tool-openocd, per host OS."""
        version = configured_packages["tool-openocd"]["version"]
        sys_type = util.get_systype()
        expected = (
            "forsilicon-openocd-apple.tar.gz" if "darwin" in sys_type else
            "forsilicon-openocd-linux.tar.gz" if "linux" in sys_type else
            "forsilicon-openocd-win.zip"
        )
        assert version == ("https://files.seeedstudio.com/arduino/platformio/"
                           + expected)

    def test_no_upstream_pruning_of_shared_packages(self, configured_packages):
        """The retired cfg's deletion bug (dropping other families'
        packages) stays fixed: neighbors keep their specs."""
        for name in ("tool-bossac", "tool-dfuutil-arduino",
                     "tool-picotool-rp2040-earlephilhower"):
            if name in configured_packages:
                assert configured_packages[name]  # still present, untouched


class TestCmsisDapDebugTool:
    @pytest.mark.parametrize(
        "board_id", ["seeed-xiao-mg24", "seeed-xiao-mg24-sense"],
        ids=lambda b: b,
    )
    def test_cmsis_dap_entry(self, siliconlab_family, board_id):
        board = board_config(board_id)
        siliconlab_family.add_default_debug_tools(None, board)
        tools = board.manifest["debug"]["tools"]
        assert "cmsis-dap" in tools
        entry = tools["cmsis-dap"]
        assert entry["server"]["package"] == "tool-openocd"
        assert entry["server"]["executable"] == "bin/openocd"
        assert entry["server"]["arguments"] == [
            "-s", "$PACKAGE_DIR/share/openocd/scripts",
            "-f", "interface/cmsis-dap.cfg",
            "-f", "target/efm32s2_g23.cfg",
            "-c", "adapter speed 1000",
        ]
        # OpenOCD has no native flash loader here: preload, then the
        # plain reset-halt sequence (mg's pattern, kept from the cfg).
        assert entry["load_cmds"] == "preload"
        assert entry["init_cmds"] == [
            "target extended-remote $DEBUG_PORT",
            "$LOAD_CMDS",
            "pio_reset_halt_target",
            "$INIT_BREAK",
        ]

    def test_missing_openocd_target_is_fatal(self, siliconlab_family):
        board = board_config("seeed-xiao-mg24")
        del board.manifest["debug"]["openocd_target"]
        with pytest.raises(AssertionError, match="Missing target"):
            siliconlab_family.add_default_debug_tools(None, board)
