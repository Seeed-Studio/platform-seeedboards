"""Upstream adapter anchor tests for the samd family.

The samd wrapper (builder/families/samd/build.py) depends on shapes of
the locked platform-atmelsam v9.0.0 checkout. Each anchor below pins
one upstream fact the adapter relies on; a failing anchor after a lock
bump means the upstream changed something the adapter assumes —
re-audit the bossac hardening graft before shipping the bump.
"""

import pathlib
import urllib.request

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in __import__("sys").path:
    __import__("sys").path.append(str(REPO))

from families import ChipFamily  # noqa: E402

_SAMD = ChipFamily.get("samd")
_LOCK_SHA = _SAMD.upstream_version.rsplit("#", 1)[-1]
_RAW = "https://raw.githubusercontent.com/platformio/platform-atmelsam"

# (path in the upstream repo, regex the adapter depends on, what it guards)
ANCHORS = (
    # the sam-ba branch sets a BARE bossac UPLOADER with no --offset —
    # the wrapper's hardening graft (absolute path + offset) rides on
    # exactly this shape
    ("builder/main.py", r'UPLOADER="bossac",',
     "sam-ba branch uses a bare bossac UPLOADER"),
    # the else-branch (non-samd51 cores) appends ["--erase", "-U",
    # "true|false"] — the graft's tail match rewrites this pair into
    # the hardened separate-flag form
    ("builder/main.py", r'"--erase",\s*"-U", "true"',
     "sam-ba else-branch appends the -U true/false pair"),
    # arduino_common builds the framework package name from
    # build.core ("framework-arduino-samd-seeed" for our boards)
    ("builder/frameworks/arduino/arduino_common.py",
     r'framework_package \+= "-%s" % board\.get\("build\.core"\)',
     "arduino_common suffixes the package name with build.core"),
    # the arduino dispatcher SConscripts its sibling by relative path —
    # resolution must land inside the upstream copy (nordic-verified
    # mechanism)
    ("builder/frameworks/arduino.py",
     r'os\.path\.join\("arduino", "arduino-%s\.py"',
     "arduino.py dispatches arduino/<mcu>.py relatively"),
    # the framework-less fallback dispatches the upstream _bare.py
    # (the local copy, byte-identical to upstream, is retired)
    ("builder/main.py", r'SConscript\("frameworks/_bare\.py"\)',
     "framework-less builds run the upstream _bare.py"),
)


def _fetch(path):
    url = "%s/%s/%s" % (_RAW, _LOCK_SHA, path)
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except OSError as exc:
        pytest.skip("upstream raw fetch failed (%s: %s) — anchor check "
                    "requires network" % (path, exc))


@pytest.mark.parametrize("path,pattern,what", ANCHORS, ids=[a[2] for a in ANCHORS])
def test_upstream_anchor(path, pattern, what):
    source = _fetch(path)
    import re
    assert re.search(pattern, source), (
        "Upstream %s no longer matches %r (%s). Re-audit the samd adapter "
        "in builder/families/samd/build.py (bossac hardening graft)."
        % (path, pattern, what))
