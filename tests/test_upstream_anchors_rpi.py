"""Upstream adapter anchor tests for the rpi family.

The rpi wrapper (builder/families/rpi/build.py) depends on shapes of
the locked maxgerhardt/platform-raspberrypi checkout. Each anchor below
pins one upstream fact the adapter relies on; a failing anchor after a
lock bump means the upstream changed something the adapter assumes —
re-audit the PATH heal and the framework dispatch before shipping the
bump.
"""

import pathlib
import urllib.request

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in __import__("sys").path:
    __import__("sys").path.append(str(REPO))

from families import ChipFamily  # noqa: E402

_RPI = ChipFamily.get("rpi")
_LOCK_SHA = _RPI.upstream_version.rsplit("#", 1)[-1]
_RAW = "https://raw.githubusercontent.com/maxgerhardt/platform-raspberrypi"

# (path in the upstream repo, regex the adapter depends on, what it guards)
ANCHORS = (
    # the custom branch must stay a pure $UPLOADCMD passthrough — the
    # wrapper's env (upload flags, PATH) is the only thing in play
    ("builder/main.py", r'upload_protocol == "custom":\s*'
                        r'upload_actions = \[env\.VerboseAction\("\$UPLOADCMD"',
     "custom branch is a pure $UPLOADCMD passthrough"),
    # generate_uf2 invokes picotool by BARE name — the wrapper's PATH
    # prepend is what makes it resolve (previously an absolute path in
    # the retired local snapshot)
    ("builder/main.py", r'"picotool",\s*"uf2",\s*"convert"',
     "generate_uf2 runs a bare-name picotool (PATH-healed by the wrapper)"),
    # the OpenOCD upload branch sets a BARE UPLOADER — second consumer
    # of the wrapper's PATH prepend
    ("builder/main.py", r'UPLOADER="openocd"',
     "openocd upload branch uses a bare UPLOADER"),
    # the picotool upload protocol itself must keep resolving through
    # get_package_dir (only generate_uf2 needs the PATH heal)
    ("builder/main.py", r'UPLOADER=join\(platform\.get_package_dir\('
                        r'"tool-picotool-rp2040-earlephilhower"\)',
     "picotool upload protocol resolves via get_package_dir"),
    # the framework-less fallback dispatches the upstream _bare.py (the
    # local copy, byte-identical to upstream, is retired)
    ("builder/main.py", r'SConscript\("frameworks/_bare\.py"\)',
     "framework-less builds run the upstream _bare.py"),
    # the arduino framework script must keep the earlephilhower branch
    # dispatching into the framework package — the retired local
    # rpi_arduino.py was exactly this branch
    ("builder/frameworks/arduino/arduino.py",
     r'if core == "earlephilhower":[\s\S]*?'
     r'get_package_dir\("framework-arduinopico"\)',
     "arduino.py earlephilhower branch dispatches to the core package"),
    # the filesystem upload target must stay registered (uploadfs rides
    # the same upload_actions as upload)
    ("builder/main.py", r'AddPlatformTarget\("uploadfs"',
     "uploadfs platform target registration"),
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
        "Upstream %s no longer matches %r (%s). Re-audit the rpi adapter "
        "in builder/families/rpi/build.py (PATH heal, framework dispatch)."
        % (path, pattern, what))
