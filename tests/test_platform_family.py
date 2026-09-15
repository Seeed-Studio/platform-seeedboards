"""Unit tests for platform.py family routing (post global-Architecture removal).

Exercises the three PlatformBase lifecycle hooks offline over the real
repository: family resolution comes from board manifests, board listing
never returns None, and debug-session dispatch resolves from the debug
config instead of module-global state.
"""

import pytest

pytest.importorskip("platformio")

from platformio.platform.factory import PlatformFactory  # noqa: E402

from verify_boards import SUPPORTED_BOARD_IDS  # noqa: E402

FAMILY_BY_PROBE_BOARD = {
    "seeed-xiao-esp32-c3": "esp",
    "seeed-xiao-nrf54lm20b": "nrf",
    "seeed-xiao-ra4m1": "renesas",
    "seeed-xiao-rp2040": "rpi",
    "seeed-xiao-samd": "samd",
    "seeed-xiao-mg24": "siliconlab",
    "seeed-xiao-stm32c5": "stm32",
}


@pytest.fixture()
def platform_instance():
    # Function-scoped on purpose: family cfg modules mutate the shared
    # packages dict cumulatively (some even delete other families' tools,
    # e.g. siliconlab_cfg), so one instance must not be reused across
    # families -- mirroring the one-process-per-pio-run reality.
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[1]
    return PlatformFactory.new(str(repo))


class TestGetBoardFamily:
    @pytest.mark.parametrize("board_id,expected", sorted(FAMILY_BY_PROBE_BOARD.items()))
    def test_probe_board_per_family(self, platform_instance, board_id, expected):
        assert platform_instance.get_board_family(board_id) == expected

    def test_every_snapshot_board_resolves(self, platform_instance):
        for board_id in SUPPORTED_BOARD_IDS:
            assert platform_instance.get_board_family(board_id)


class TestGetBoardsListing:
    def test_all_boards_listed_non_none(self, platform_instance):
        boards = platform_instance.get_boards()
        assert set(boards) == set(SUPPORTED_BOARD_IDS)
        for board_id, board in boards.items():
            assert board is not None, board_id
            assert board.get_brief_data()["id"] == board_id

    def test_add_dynamic_options_returns_board_object(self, platform_instance):
        boards = platform_instance.get_boards()
        for board_id, board in boards.items():
            result = platform_instance._add_dynamic_options(board)
            assert result is not None, board_id
            assert result.id == board_id
            # family debug tools were injected
            assert result.manifest.get("debug", {}).get("tools")


class TestConfigureDefaultPackages:
    # Core passes the ini's framework list under both "framework" and
    # "pioframework" (see PlatformBase.configure_project_packages).
    @pytest.mark.parametrize(
        "board_id", sorted(FAMILY_BY_PROBE_BOARD), ids=lambda b: b
    )
    def test_one_board_per_family_configures(self, platform_instance, board_id):
        # dispatches to the family cfg module without raising
        platform_instance.configure_default_packages(
            {"board": board_id, "framework": ["arduino"], "pioframework": ["arduino"]},
            [],
        )

    def test_esp_probe_enables_riscv_toolchain(self, platform_instance):
        platform_instance.configure_default_packages(
            {
                "board": "seeed-xiao-esp32-c3",
                "framework": ["arduino"],
                "pioframework": ["arduino"],
            },
            [],
        )
        assert platform_instance.packages["toolchain-riscv32-esp"]["optional"] is False

    def test_samd_probe_enables_bossac(self, platform_instance):
        platform_instance.configure_default_packages(
            {
                "board": "seeed-xiao-samd",
                "framework": ["arduino"],
                "pioframework": ["arduino"],
            },
            [],
        )
        assert platform_instance.packages["tool-bossac"]["optional"] is False

    def test_nrf_zephyr_enables_build_tools(self, platform_instance):
        platform_instance.configure_default_packages(
            {
                "board": "seeed-xiao-nrf54lm20b",
                "framework": ["zephyr"],
                "pioframework": ["zephyr"],
            },
            [],
        )
        assert platform_instance.packages["tool-cmake"]["optional"] is False
        assert platform_instance.packages["tool-ninja"]["optional"] is False
        assert platform_instance.packages["toolchain-gccarmnoneeabi"]["optional"] is False


class TestConfigureDebugSession:
    def test_no_board_config_is_noop(self, platform_instance):
        class StubDebugConfig:
            board_config = {}
            speed = None

        # must not raise even though no family context exists
        platform_instance.configure_debug_session(StubDebugConfig())

    def test_debug_session_dispatches_for_samd(self, platform_instance):
        from platformio.platform.board import PlatformBoardConfig
        import pathlib

        repo = pathlib.Path(__file__).resolve().parents[1]
        config = PlatformBoardConfig(
            str(repo / "boards" / "seeed-xiao-samd.json")
        )

        class StubDebugConfig:
            board_config = config
            speed = None
            server = {"executable": "", "arguments": []}

        # configure_samd_debug_session dispatches on server executable only;
        # with an empty executable it returns without touching anything.
        platform_instance.configure_debug_session(StubDebugConfig())
