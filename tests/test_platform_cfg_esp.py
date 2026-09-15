"""Unit tests for platform_cfg/esp_cfg.py debug-tool injection.

Loads esp_cfg standalone via importlib (the repo root must not land on
sys.path: its platform.py would shadow the stdlib platform module for
platformio's import chain).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("platformio")

from platformio.platform.board import PlatformBoardConfig  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


def load_esp_cfg():
    spec = importlib.util.spec_from_file_location(
        "esp_cfg_under_test", REPO / "platform_cfg" / "esp_cfg.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def esp_cfg():
    return load_esp_cfg()


def board_config(board_id):
    return PlatformBoardConfig(str(REPO / "boards" / f"{board_id}.json"))


class TestEspBuiltinDebugTool:
    @pytest.mark.parametrize(
        "board_id",
        ["seeed-xiao-esp32-c3", "seeed-xiao-esp32-c5", "seeed-xiao-esp32-c6"],
        ids=lambda b: b,
    )
    def test_riscv_boards_get_esp_builtin(self, esp_cfg, board_id):
        board = board_config(board_id)
        esp_cfg._add_esp_default_debug_tools(object(), board)
        assert "esp-builtin" in board.get("upload.protocols")
        assert "esp-builtin" in board.manifest["debug"]["tools"]

    def test_s3_gets_esp_builtin(self, esp_cfg):
        board = board_config("seeed-xiao-esp32-s3-sense")
        esp_cfg._add_esp_default_debug_tools(object(), board)
        assert "esp-builtin" in board.get("upload.protocols")

    def test_upload_protocols_populated(self, esp_cfg):
        board = board_config("seeed-xiao-esp32-c5")
        esp_cfg._add_esp_default_debug_tools(object(), board)
        assert "esptool" in board.get("upload.protocols")
        assert board.get("upload.protocol")
