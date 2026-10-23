"""Upstream adapter anchor tests.

The ESP32 family mounts host-side adapters that depend on
implementation details of the locked pioarduino package (see the
adapter list in Esp32Family's class header). These tests are the
sentinel for lock bumps: they fetch the anchor files at the LOCKED
commit from GitHub raw and assert each detail still holds. A failure
here means an upstream upgrade changed something an adapter relies on —
re-audit the adapter points before merging, instead of discovering a
broken (or silently misbehaving) build later.

Network-dependent: skipped when raw.githubusercontent.com is
unreachable (offline dev machines).
"""

import pathlib
import re
import urllib.request

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in __import__("sys").path:
    __import__("sys").path.append(str(REPO))

from families import ChipFamily  # noqa: E402

_ESP32 = ChipFamily.get("esp32")
_LOCK_SHA = _ESP32.upstream_version.rsplit("#", 1)[-1]
_RAW = "https://raw.githubusercontent.com/pioarduino/platform-espressif32"

# (path in the upstream repo, regex the adapter depends on, what it guards)
ANCHORS = (
    ("builder/main.py", r"platform\.setup_python_env\(",
     "main.py calls platform.setup_python_env — the host-method adapter"),
    ("builder/main.py", r"get_dir\(\)",
     "main.py resolves companion paths via get_dir() — UpstreamPlatformProxy"),
    ("builder/main.py", r"spiffsgen\.py",
     "spiffsgen companion path via the platform dir"),
    ("builder/frameworks/espidf.py", r"component_manager\.py",
     "component_manager companion path via get_dir()"),
    ("builder/frameworks/espidf.py", r"penv_setup\.py",
     "penv_setup companion path via get_dir()"),
    ("platform.py", r"def install_tool",
     "install_tool API — the stub-expansion adapter"),
    ("builder/penv_setup.py", r"python_deps",
     "python_deps declaration — the penv seed adapter"),
)


def _fetch(path):
    url = "%s/%s/%s" % (_RAW, _LOCK_SHA, path)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except OSError as exc:
        pytest.skip("upstream raw fetch failed (%s: %s) — anchor check "
                    "requires network" % (path, exc))


@pytest.mark.parametrize("path,pattern,what", ANCHORS, ids=[a[2][:40] for a in ANCHORS])
def test_upstream_anchor(path, pattern, what):
    source = _fetch(path)
    assert re.search(pattern, source), (
        "Adapter anchor drifted at locked commit %s (%s)\n"
        "  %s no longer matches /%s/\n"
        "Re-audit the adapter list in Esp32Family (families/espressif.py)."
        % (_LOCK_SHA[:7], path, what, pattern)
    )
