"""Unit tests for scripts/ci/clean_zephyr_views.py."""

import os
from pathlib import Path

from clean_zephyr_views import VIEW_MARKER, collect_views, prune_views


def _view(root, name, age):
    path = root / name
    path.mkdir(parents=True)
    (path / VIEW_MARKER).write_text("key", encoding="utf-8")
    os.utime(path, (age, age))
    return path


def test_collect_requires_marker(tmp_path):
    view = _view(tmp_path, "v1", 1000)
    (tmp_path / "not-a-view").mkdir()
    assert collect_views(tmp_path) == [view]


def test_prune_keeps_newest(tmp_path):
    old = _view(tmp_path, "old", 1000)
    mid = _view(tmp_path, "mid", 2000)
    new = _view(tmp_path, "new", 3000)
    kept, removed = prune_views(tmp_path, keep=1)
    assert kept == [new]
    assert removed == [mid, old]
    assert new.exists() and not mid.exists() and not old.exists()


def test_prune_dry_run_keeps_files(tmp_path):
    _view(tmp_path, "old", 1000)
    _view(tmp_path, "new", 2000)
    kept, removed = prune_views(tmp_path, keep=1, dry_run=True)
    assert len(kept) == 1 and len(removed) == 1
    assert all(path.exists() for path in [*kept, *removed])


def test_empty_root(tmp_path):
    assert collect_views(tmp_path / "missing") == []