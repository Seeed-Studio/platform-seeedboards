"""Shared fixtures: put the repo root and families package on sys.path.

NOTE: run pytest via the console script from the repo root -- once
platform.py exists at the root, `python -m pytest` would put the root
on sys.path and platform.py would shadow the stdlib platform module.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for entry in (str(REPO_ROOT), str(REPO_ROOT / "scripts" / "ci")):
    if entry not in sys.path:
        sys.path.insert(0, entry)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT
