"""Unit tests for the runtime platform contract gate."""

import pytest

pytest.importorskip("platformio")

from verify_platform import verify_repo  # noqa: E402


def test_repo_platform_contract_clean():
    assert verify_repo() == []