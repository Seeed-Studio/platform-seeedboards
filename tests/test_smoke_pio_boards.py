"""Unit test wrapper for scripts/ci/smoke_pio_boards.py.

Skips automatically when the platformio package is not importable so the
suite stays runnable in bare environments; CI installs platformio.
"""

import pytest

pytest.importorskip("platformio")

import smoke_pio_boards  # noqa: E402  (needs conftest's sys.path entry)


def test_smoke_over_repo():
    assert smoke_pio_boards.main() == 0
