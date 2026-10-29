"""Upstream adapter anchor tests for the Nordic family.

The nordic wrapper (builder/families/nordic/build.py) and upload layer
(builder/families/nordic/upload.py) depend on shapes of the locked
platform-nordicnrf52 checkout. Each anchor below pins one upstream
fact the adapter relies on; a failing anchor after a lock bump means
the upstream changed something an adapter assumes — re-audit the
takeover rules in upload.py before shipping the bump.
"""

import pathlib
import urllib.request

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in __import__("sys").path:
    __import__("sys").path.append(str(REPO))

from families import ChipFamily  # noqa: E402

_NRF = ChipFamily.get("nrf")
_LOCK_SHA = _NRF.upstream_version.rsplit("#", 1)[-1]
_RAW = "https://raw.githubusercontent.com/platformio/platform-nordicnrf52"

# (path in the upstream repo, regex the adapter depends on, what it guards)
ANCHORS = (
    # the custom branch must stay a pure $UPLOADCMD passthrough — the
    # whole takeover design rides on it
    ("builder/main.py", r'upload_protocol == "custom":\s*'
                        r'upload_actions = \[env\.VerboseAction\("\$UPLOADCMD"',
     "custom branch is a pure $UPLOADCMD passthrough"),
    # the upstream dispatch must keep reading $UPLOAD_PROTOCOL from the
    # env so the wrapper's pre-script rewrite is honored
    ("builder/main.py", r'upload_protocol = env\.subst\("\$UPLOAD_PROTOCOL"\)',
     "upload dispatch reads $UPLOAD_PROTOCOL from the env"),
    # ElfToBin must stay registered unconditionally (the graft functions
    # rely on it for every takeover artifact chain)
    ("builder/main.py", r'ElfToBin=Builder\(',
     "ElfToBin builder registration"),
    # the zephyr build-pre shim is SConscripted from the framework-zephyr
    # package — the single-package unification (PR-1) keyed on this
    ("builder/main.py", r'"framework-zephyr"\), "scripts", "platformio",'
                        r'\s*"platformio-build-pre\.py"',
     "zephyr build-pre loaded from the framework-zephyr package"),
    # the framework-less fallback dispatches the upstream _bare.py (the
    # local copy is retired)
    ("builder/main.py", r'SConscript\("frameworks/_bare\.py"\)',
     "framework-less builds run the upstream _bare.py"),
    # the J-Link uploader path fix (2025-10-23) we inherited with the
    # lock — quoted script path on the command line
    ("builder/main.py", r'-CommanderScript "\$\{__jlink_cmd_script',
     "J-Link upload script path is quoted"),
    # the adafruit framework script must resolve its package through
    # get_package_dir — the proxy forwards that to the host platform
    ("builder/frameworks/arduino/adafruit.py",
     r'get_package_dir\("framework-arduinoadafruitnrf52"\)',
     "adafruit.py resolves its BSP package via get_package_dir"),
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
        "Upstream %s no longer matches %r (%s). Re-audit the nordic "
        "adapters in builder/families/nordic/ (see handover: takeover rules)."
        % (path, pattern, what))
