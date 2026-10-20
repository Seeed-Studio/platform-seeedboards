"""Unit tests for platform_cfg/esp_cfg.py debug-tool injection.

platformio is imported first (importorskip above) so the stdlib platform
module is already cached in sys.modules; the repo root is then appended --
not prepended -- to sys.path so platform_cfg is importable without letting
the repo's platform.py shadow the stdlib for any later import.
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("platformio")

from platformio.platform.board import PlatformBoardConfig  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.append(str(REPO))

from platform_cfg import EspConfig  # noqa: E402


def board_config(board_id):
    return PlatformBoardConfig(str(REPO / "boards" / f"{board_id}.json"))


class TestEspBuiltinDebugTool:
    @pytest.mark.parametrize(
        "board_id",
        ["seeed-xiao-esp32-c3", "seeed-xiao-esp32-c5", "seeed-xiao-esp32-c6"],
        ids=lambda b: b,
    )
    def test_riscv_boards_get_esp_builtin(self, board_id):
        board = board_config(board_id)
        EspConfig(object()).add_default_debug_tools(board)
        assert "esp-builtin" in board.get("upload.protocols")
        assert "esp-builtin" in board.manifest["debug"]["tools"]

    def test_s3_gets_esp_builtin(self):
        board = board_config("seeed-xiao-esp32-s3-sense")
        EspConfig(object()).add_default_debug_tools(board)
        assert "esp-builtin" in board.get("upload.protocols")

    def test_upload_protocols_populated(self):
        board = board_config("seeed-xiao-esp32-c5")
        EspConfig(object()).add_default_debug_tools(board)
        assert "esptool" in board.get("upload.protocols")
        assert board.get("upload.protocol")
