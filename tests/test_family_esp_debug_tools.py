"""Unit tests for the Esp32Family debug-tool injection.

The behavior was inlined from the retired platform_cfg/esp_cfg.py; the
family class now owns it. The repo root lands on sys.path tail-append
only (its platform.py must not shadow the stdlib platform module for
platformio's import chain).
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("platformio")

from platformio.platform.board import PlatformBoardConfig  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))

from families import ChipFamily  # noqa: E402


@pytest.fixture(scope="module")
def esp32_family():
    return ChipFamily.get("esp32")


def board_config(board_id):
    return PlatformBoardConfig(str(REPO / "boards" / f"{board_id}.json"))


class TestEspBuiltinDebugTool:
    @pytest.mark.parametrize(
        "board_id",
        ["seeed-xiao-esp32-c3", "seeed-xiao-esp32-c5", "seeed-xiao-esp32-c6"],
        ids=lambda b: b,
    )
    def test_riscv_boards_get_esp_builtin(self, esp32_family, board_id):
        board = board_config(board_id)
        esp32_family.add_default_debug_tools(None, board)
        assert "esp-builtin" in board.get("upload.protocols")
        assert "esp-builtin" in board.manifest["debug"]["tools"]

    def test_s3_gets_esp_builtin(self, esp32_family):
        board = board_config("seeed-xiao-esp32-s3-sense")
        esp32_family.add_default_debug_tools(None, board)
        assert "esp-builtin" in board.get("upload.protocols")

    def test_upload_protocols_populated(self, esp32_family):
        board = board_config("seeed-xiao-esp32-c5")
        esp32_family.add_default_debug_tools(None, board)
        assert "esptool" in board.get("upload.protocols")
        assert board.get("upload.protocol")
