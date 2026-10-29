"""Upstream adapter anchor tests for the renesas family.

The renesas wrapper (builder/families/renesas/build.py + upload.py)
depends on shapes of the locked platform-renesas-ra v1.9.0 checkout.
Each anchor below pins one upstream fact the adapter relies on; a
failing anchor after a lock bump means the upstream changed something
the adapter assumes — re-audit the pyocd hex graft and the bossac
hardening before shipping the bump.
"""

import pathlib
import urllib.request

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
if str(REPO) not in __import__("sys").path:
    __import__("sys").path.append(str(REPO))

from families import ChipFamily  # noqa: E402

_RENESAS = ChipFamily.get("renesas")
_LOCK_SHA = _RENESAS.upstream_version.rsplit("#", 1)[-1]
_RAW = "https://raw.githubusercontent.com/platformio/platform-renesas-ra"

# (path in the upstream repo, regex the adapter depends on, what it guards)
ANCHORS = (
    # the takeover rewrites UPLOAD_PROTOCOL to "custom"; the upstream
    # branch must remain a pure $UPLOADCMD passthrough for the
    # pre-configured pyocd command to ride it
    ("builder/main.py",
     r'upload_protocol == "custom":\s*'
     r'upload_actions = \[env\.VerboseAction\("\$UPLOADCMD"',
     "custom branch is a pure $UPLOADCMD passthrough"),
    # the protocol is read from the SCons env, so the takeover's
    # env.Replace(UPLOAD_PROTOCOL="custom") steers the dispatch
    ("builder/main.py", r'upload_protocol = env\.subst\("\$UPLOAD_PROTOCOL"\)',
     "protocol read from the SCons env"),
    # the upstream dispatch always registers the plain .bin as
    # target_firm — without the hex graft, pyocd would flash the bin
    # over the bootloader at 0x0
    ("builder/main.py", r'target_firm = env\.ElfToBin\(',
     "target_firm defaults to the plain .bin (hex graft is mandatory)"),
    # the graft builds the hex through the upstream-registered builder
    ("builder/main.py", r'ElfToHex=Builder\(',
     "ElfToHex builder registered (graft uses it)"),
    # the framework-less fallback dispatches the upstream _bare.py
    # (the local copy, byte-identical to upstream, is retired)
    ("builder/main.py", r'SConscript\("frameworks/_bare\.py"\)',
     "framework-less builds run the upstream _bare.py"),
    # jlink rides the upstream branch untouched; its script-path
    # UPLOADCMD must keep working from the wrapper context
    ("builder/main.py",
     r'-CommanderScript "\$\{__jlink_cmd_script\(__env__, SOURCE\)\}"',
     "jlink branch keeps the quoted script-path UPLOADCMD"),
    # the upstream arduino script resolves our Seeed tarball through
    # the registry package name (nordic adafruit-BSP mechanism)
    ("builder/frameworks/arduino.py",
     r'FRAMEWORK_DIR = platform\.get_package_dir\('
     r'"framework-arduinorenesas-uno"\)',
     "arduino.py resolves the uno framework package by name"),
    # the dfu branch (ra4m1's default protocol) rides upstream as-is
    ("builder/main.py", r'get_package_dir\("tool-dfuutil-arduino"\)',
     "dfu branch resolves dfu-util from tool-dfuutil-arduino"),
    # the sam-ba branch sets a BARE bossac UPLOADER with hard-coded
    # flags — the hardening graft (explicit path, --verify, --offset)
    # replaces exactly this shape
    ("builder/main.py", r'UPLOADER="bossac",',
     "sam-ba branch uses a bare bossac UPLOADER"),
    ("builder/main.py",
     r'"--usb-port",\s*"--erase",\s*"--write",\s*"--reset"',
     "sam-ba flags hard-coded without --verify/--offset"),
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
        "Upstream %s no longer matches %r (%s). Re-audit the renesas adapter "
        "in builder/families/renesas/build.py + upload.py (pyocd hex graft, "
        "bossac hardening)." % (path, pattern, what))


def test_upstream_has_no_pyocd_branch():
    """The takeover's whole justification: upstream dispatches no pyocd.

    If upstream grows a pyocd branch, our takeover shadows it — re-audit
    which of the two should own the protocol before a lock bump."""
    source = _fetch("builder/main.py")
    assert "pyocd" not in source, (
        "Upstream builder/main.py now mentions pyocd — our takeover "
        "(builder/families/renesas/upload.py) would shadow an upstream "
        "pyocd branch. Re-audit before the lock bump.")
