"""Unit tests for scripts/ci/verify_workflows.py."""

import pytest

yaml = pytest.importorskip("yaml")

from verify_workflows import check_workflows  # noqa: E402


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_valid_workflow(tmp_path):
    _write(tmp_path / "ci.yml", """
name: CI
on:
  push:
    branches: [v3]
permissions:
  contents: read
jobs: {}
""")
    assert check_workflows(tmp_path) == []


def test_missing_permissions(tmp_path):
    _write(tmp_path / "ci.yml", """
name: CI
on:
  push:
    branches: [v3]
jobs: {}
""")
    assert any("permissions" in e for e in check_workflows(tmp_path))


def test_missing_v3_push_branch(tmp_path):
    _write(tmp_path / "ci.yml", """
name: CI
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs: {}
""")
    assert any("v3" in e for e in check_workflows(tmp_path))


def test_undefined_alias_is_reported(tmp_path):
    _write(tmp_path / "ci.yml", """
name: CI
on:
  push:
    branches: [v3]
    paths: &p
      - 'a'
  pull_request:
    paths: *missing
permissions:
  contents: read
jobs: {}
""")
    assert any("YAML parse failed" in e for e in check_workflows(tmp_path))