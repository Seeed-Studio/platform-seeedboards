"""Unit tests for scripts/ci/verify_core.py -- the zero-string gate."""

from verify_core import verify_platform_json, verify_zero_string


class TestZeroString:
    def test_core_files_clean(self):
        assert verify_zero_string() == []


class TestPlatformJson:
    def test_platform_json_valid(self, repo_root):
        assert verify_platform_json() == []
