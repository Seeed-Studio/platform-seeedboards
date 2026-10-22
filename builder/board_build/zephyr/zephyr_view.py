"""Per-build Zephyr framework views and atomic file helpers.

ADR-0006: fixes must never mutate the global PlatformIO package cache.
`ensure_view()` creates a hardlink copy of the installed framework package
under the project core directory; the Zephyr build then writes only into
that view. Atomic helpers keep hardlinked source files intact: writing a
temporary file and `os.replace`-ing it breaks the link instead of truncating
the shared inode.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

_VIEW_KEY = ".pio-view-key"


def _hash_file(digest, path: Path, label: str) -> None:
    st = path.stat()
    digest.update(label.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(st.st_size).encode("ascii"))
    digest.update(b"\0")
    digest.update(str(st.st_mtime_ns).encode("ascii"))
    digest.update(b"\0")


def digest_paths(paths) -> str:
    """Stable short digest of files/directories used as view key material."""
    digest = hashlib.sha256()
    for raw in paths:
        path = Path(raw)
        digest.update(b"root\0")
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        if not path.exists():
            digest.update(b"missing\0")
            continue
        if path.is_file():
            _hash_file(digest, path, path.name)
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for name in sorted(filenames):
                if name.endswith(".pyc"):
                    continue
                file_path = Path(dirpath) / name
                try:
                    rel = file_path.relative_to(path).as_posix()
                    _hash_file(digest, file_path, rel)
                except OSError:
                    continue
    return digest.hexdigest()[:16]


def _preserve_mode(source: Path, target: Path) -> None:
    try:
        mode = stat.S_IMODE(source.stat().st_mode)
    except OSError:
        return
    try:
        os.chmod(target, mode)
    except OSError:
        pass


def atomic_write_text(path, text: str, *, encoding: str = "utf-8",
                      newline: str = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".pio-atomic-", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline=newline) as handle:
            handle.write(text)
        if path.exists():
            _preserve_mode(path, tmp)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write_bytes(path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".pio-atomic-", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if path.exists():
            _preserve_mode(path, tmp)
        else:
            os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_copy(source, destination) -> None:
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".pio-atomic-",
                                    dir=str(destination.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(source, tmp)
        os.replace(tmp, destination)
    finally:
        tmp.unlink(missing_ok=True)


def _link_or_copy(source: str, destination: str) -> None:
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


class _ViewLock:
    """Cross-process lock for view creation (POSIX flock / Windows msvcrt)."""

    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        try:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            try:
                import msvcrt
                self.handle.seek(0)
                if self.handle.tell() == 0:
                    self.handle.write(b"\0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
            except (ImportError, OSError):
                pass
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.handle is None:
            return False
        try:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            try:
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            except (ImportError, OSError):
                pass
        self.handle.close()
        return False


def ensure_view(source_dir, cache_root, key: str, *, prefix: str,
                log=print) -> str:
    """Return a writable hardlink view of `source_dir` for this build."""
    source = Path(source_dir).resolve()
    if not source.is_dir():
        raise RuntimeError("Zephyr framework package is missing: %s" % source)
    cache = Path(cache_root)
    cache.mkdir(parents=True, exist_ok=True)

    safe_prefix = "".join(c if c.isalnum() or c in "-_." else "_"
                          for c in prefix)[:80]
    target = cache / ("%s-%s" % (safe_prefix, key))
    marker = target / _VIEW_KEY
    try:
        if marker.is_file() and marker.read_text(encoding="utf-8") == key:
            return str(target)
    except OSError:
        pass

    with _ViewLock(cache / ("%s.lock" % safe_prefix)):
        try:
            if marker.is_file() and marker.read_text(encoding="utf-8") == key:
                return str(target)
        except OSError:
            pass

        tmp = Path(tempfile.mkdtemp(prefix=".view-", dir=str(cache)))
        shutil.rmtree(tmp)
        try:
            shutil.copytree(
                source, tmp, symlinks=True,
                copy_function=_link_or_copy,
                ignore_dangling_symlinks=True,
            )
            atomic_write_text(tmp / _VIEW_KEY, key)
            if target.exists():
                shutil.rmtree(target)
            os.replace(tmp, target)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        log("Zephyr framework view: %s" % target)
        return str(target)


if __name__ == "__main__":  # pragma: no cover - diagnostic helper
    if len(sys.argv) != 4:
        raise SystemExit("usage: zephyr_view.py <source> <cache> <key>")
    print(ensure_view(sys.argv[1], sys.argv[2], sys.argv[3],
                      prefix="manual"))