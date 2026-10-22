"""Unit tests for scripts/ci/verify_core.py -- the zero-string gate."""

import json

from verify_core import verify_platform_json, verify_zero_string


class TestZeroString:
    def test_core_files_clean(self):
        assert verify_zero_string() == []

    def test_chip_literal_counterexample(self, tmp_path):
        (tmp_path / "platform.py").write_text('CHIP = "esp32"\n', encoding="utf-8")
        errors = verify_zero_string(tmp_path, ("platform.py",))
        assert any("esp32" in error for error in errors)

    def test_missing_core_file(self, tmp_path):
        errors = verify_zero_string(tmp_path, ("missing.py",))
        assert any("not found" in error for error in errors)


class TestPlatformJson:
    def test_platform_json_valid(self, repo_root):
        assert verify_platform_json() == []

    def test_missing_framework_script(self, tmp_path):
        (tmp_path / "platform.json").write_text(json.dumps({
            "frameworks": {"arduino": {"script": "missing.py"}}
        }), encoding="utf-8")
        errors = verify_platform_json(tmp_path)
        assert any("missing.py" in error for error in errors)
