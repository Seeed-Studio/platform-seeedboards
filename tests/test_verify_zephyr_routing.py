"""Unit tests for scripts/ci/verify_zephyr_routing.py."""

from verify_zephyr_routing import (  # noqa: E402
    verify_fixes_layout,
    verify_zephyr_routing,
)


def _fixes_tree(tmp_path):
    arm = tmp_path / "boards" / "arm"
    fixes = arm / "b" / "fixes"
    fixes.mkdir(parents=True)
    (fixes / "drivers").mkdir()
    (fixes / "drivers" / "x.c").write_text("override\n", encoding="utf-8")
    (fixes / "fixes.baseline").write_text(
        "drivers/x.c " + "a" * 64 + "\n", encoding="utf-8")
    return arm


def test_fixes_layout_valid(tmp_path):
    assert verify_fixes_layout(_fixes_tree(tmp_path), {"b"}) == []


def test_fixes_layout_missing_baseline(tmp_path):
    arm = _fixes_tree(tmp_path)
    (arm / "b" / "fixes" / "fixes.baseline").unlink()
    errors = verify_fixes_layout(arm, {"b"})
    assert any("no fixes.baseline" in e for e in errors)


def test_fixes_layout_fix_without_entry(tmp_path):
    arm = _fixes_tree(tmp_path)
    (arm / "b" / "fixes" / "fixes.baseline").write_text("", encoding="utf-8")
    errors = verify_fixes_layout(arm, {"b"})
    assert any("has no fixes.baseline entry" in e for e in errors)


def test_fixes_layout_orphan_baseline_entry(tmp_path):
    arm = _fixes_tree(tmp_path)
    (arm / "b" / "fixes" / "drivers" / "x.c").unlink()
    errors = verify_fixes_layout(arm, {"b"})
    assert any("with no fix file" in e for e in errors)


def test_fixes_layout_unknown_board(tmp_path):
    arm = _fixes_tree(tmp_path)
    errors = verify_fixes_layout(arm, {"other"})
    assert any("no board declares this board_name" in e for e in errors)


def test_routing_chain_closed(tmp_path):
    zephyr_root = tmp_path / "zephyr"
    (zephyr_root / "boards" / "arm" / "b").mkdir(parents=True)
    boards = {"b": {"package": "framework-zephyr-x", "board_name": "b"}}
    assert verify_zephyr_routing(boards, {"framework-zephyr-x"}, zephyr_root) == []


def test_routing_missing_package_and_tree(tmp_path):
    zephyr_root = tmp_path / "zephyr"
    (zephyr_root / "boards" / "arm").mkdir(parents=True)
    boards = {"b": {"package": "framework-zephyr-missing", "board_name": "b"}}
    errors = verify_zephyr_routing(boards, {"framework-zephyr-x"}, zephyr_root)
    assert any("not declared in platform.json" in e for e in errors)
    assert any("no zephyr/boards/arm/b" in e for e in errors)