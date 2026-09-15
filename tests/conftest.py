"""Shared pytest fixtures for platform-seeedboards offline gates.

Puts scripts/ci on sys.path so tests import the verify_* modules directly
(same directory-import style the scripts themselves use), and exposes the
repository layout.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_CI_DIR = REPO_ROOT / "scripts" / "ci"

if str(SCRIPTS_CI_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_CI_DIR))


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def repo_platform_frameworks() -> set:
    from verify_boards import load_platform_frameworks

    return load_platform_frameworks(REPO_ROOT / "platform.json")


@pytest.fixture(scope="session")
def valid_boards_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "boards" / "valid"
