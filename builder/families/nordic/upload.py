# Copyright 2026-present Seeed Studio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Upload-layer deltas for the Nordic family (moved from the retired
nrf_build.py; behavior is unchanged).

The upstream builder skeleton dispatches upload protocols it knows
(nrfutil, nrfjprog, mbed, sam-ba, jlink, blackmagic, OpenOCD-via-debug-
tools, custom). Where our behavior differs, the PROTOCOLS registry at
the bottom of this module takes the upload over: build.py resolves the
protocol, pre-configures the full uploader command, rewrites
UPLOAD_PROTOCOL to "custom" so the upstream dispatch degrades to a pure
``VerboseAction("$UPLOADCMD")`` passthrough, and — after the upstream
script has registered its upload target — grafts our artifact chain
(hex is the upstream custom-branch default; several of our protocols
flash bin/signed images instead).

This module is a regular Python import (not SCons-exec'd), so plain
``__file__`` anchors are safe here.
"""

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from os.path import dirname, isfile, join
from platform import machine, system
from urllib.request import urlretrieve


_NRFUTIL_VERSION = "8.2.0"
_NRFUTIL_MCUMGR_VERSION = "0.9.0"
_NRFUTIL_DOWNLOAD_URL = "https://developer.nordicsemi.com/.pc-tools/nrfutil/%s-%s-%s.tar.gz"

# USB CDC identities for the nrfutil-mcumgr upload path (app/loader
# VID:PID) are declared per board in the manifest's upload.cdc; the port
# resolution, 1200-bps touch and loader-CDC wait live in
# mcumgrupload.py (this directory), which runs as a child console
# process so Ctrl+C can interrupt every wait.
_UPLOADER_DIR = dirname(__file__)


def _nrfutil_target():
    """Return Nordic's target triple for the host running PlatformIO."""
    host_os = system().lower()
    host_machine = machine().lower()
    if host_os == "windows" and host_machine in ("amd64", "x86_64"):
        return "x86_64-pc-windows-msvc"
    if host_os == "linux" and host_machine in ("amd64", "x86_64"):
        return "x86_64-unknown-linux-gnu"
    if host_os == "darwin" and host_machine in ("arm64", "aarch64"):
        return "aarch64-apple-darwin"
    if host_os == "darwin" and host_machine in ("x86_64", "amd64"):
        return "x86_64-apple-darwin"
    return None


def _nrfutil_supports_mcumgr(executable, process_env=None):
    try:
        subprocess.check_call(
            [executable, "mcu-manager", "serial", "image-upload", "--help"],
            env=process_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _safe_extract_tarball(tarball_path, destination):
    """Extract an official nrfutil archive without permitting path traversal."""
    destination = os.path.realpath(destination)
    with tarfile.open(tarball_path, "r:gz") as archive:
        for member in archive.getmembers():
            member_path = os.path.realpath(join(destination, member.name))
            if member_path != destination and not member_path.startswith(destination + os.sep):
                raise RuntimeError("Unsafe path in nrfutil archive: %s" % member.name)
        archive.extractall(destination)


def _ensure_nrfutil_installed(env):
    """Return nrfutil v8 with mcu-manager without altering PlatformIO's venv.

    The legacy PyPI ``nrfutil`` package is capped at v5 and depends on Click
    7, while PlatformIO Core needs Click 8.  Nordic's v8 CLI is a standalone
    executable, so keep it in PlatformIO's tool cache rather than using pip.
    """
    system_nrfutil = shutil.which("nrfutil")
    if system_nrfutil and _nrfutil_supports_mcumgr(system_nrfutil):
        return system_nrfutil

    target = _nrfutil_target()
    if not target:
        sys.stderr.write(
            "Error: automatic Nordic nrfutil installation is unsupported on "
            "%s/%s. Install nrfutil 8 with the mcu-manager command manually.\n" %
            (system(), machine()))
        env.Exit(1)

    nrfutil_home = join(env.subst("$PROJECT_CORE_DIR"), "nrfutil")
    install_root = join(nrfutil_home, "nrfutil-%s-%s" % (_NRFUTIL_VERSION, target))
    executable = join(
        install_root, "nrfutil-%s-%s" % (target, _NRFUTIL_VERSION), "data", "bin",
        "nrfutil.exe" if system() == "Windows" else "nrfutil")
    marker = join(install_root, "mcu-manager-%s.installed" % _NRFUTIL_MCUMGR_VERSION)
    process_env = os.environ.copy()
    process_env["NRFUTIL_HOME"] = nrfutil_home

    try:
        if not isfile(executable):
            temporary_dir = tempfile.mkdtemp()
            try:
                mcumgr_archive = join(temporary_dir, "mcu-manager.tar.gz")
                urlretrieve(_NRFUTIL_DOWNLOAD_URL % (
                    _NRFUTIL_VERSION, target, _NRFUTIL_MCUMGR_VERSION), mcumgr_archive)
                subprocess.check_call(
                    [executable, "install", "--tarball", mcumgr_archive], env=process_env)
            finally:
                shutil.rmtree(temporary_dir, ignore_errors=True)
        if not _nrfutil_supports_mcumgr(executable, process_env):
            subprocess.check_call(
                [executable, "install", "mcu-manager=%s" % _NRFUTIL_MCUMGR_VERSION],
                env=process_env)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
        sys.stderr.write("Error: failed to install Nordic nrfutil: %s\n" % exc)
        env.Exit(1)

    if not _nrfutil_supports_mcumgr(executable, process_env):
        sys.stderr.write("Error: Nordic nrfutil mcu-manager installation is incomplete.\n")
        env.Exit(1)

    env["ENV"]["NRFUTIL_HOME"] = nrfutil_home
    return executable


def _ensure_pyocd_installed(env):
    # Official pyOCD: it has shipped the nRF54LM20A target since v0.44.0
    # (pyocd/pyOCD#1889). `pyocd flash` on nRF54LM20A still faults: the
    # builtin algorithm programs RRAM with the RRAMC write buffer
    # unconfigured (pyocd/pyOCD#2016); the fix is pending in
    # pyocd/pyOCD#2033 -- bump this pin once that ships in a release and
    # pyocd flash becomes usable. Until then the LM20A upload path uses
    # OpenOCD; pyocd serves list/rtt/erase.
    pyocd_version = "0.45.1"
    pyocd_spec = "pyocd==%s" % pyocd_version

    def _installed_pyocd_is_expected():
        try:
            python_exe = sys.executable
            # Version check first: the retired StarSphere fork also exposes
            # the nrf54lm20a target, so the target check alone cannot tell
            # the two apart and would silently keep the fork installed.
            version = subprocess.check_output(
                [python_exe, "-m", "pyocd", "--version"]).decode("utf-8").strip()
            if pyocd_version not in version:
                return False
            output = subprocess.check_output(
                [python_exe, "-m", "pyocd", "list", "--targets"]).decode("utf-8")
            return "nrf54lm20a" in output.lower()
        except (OSError, subprocess.CalledProcessError):
            return False

    if _installed_pyocd_is_expected():
        return

    python_exe = env.subst("$PYTHONEXE")
    print("[INFO] Installing official pyOCD %s..." % pyocd_version)
    subprocess.check_call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([
        python_exe,
        "-m", "pip", "install", "--upgrade", pyocd_spec, "libusb",
    ])


def _get_dfu_upload_offset(board_config):
    upload_offset = board_config.get("upload.offset_address", None)
    if upload_offset:
        return upload_offset

    from os.path import basename
    ldscript = basename(
        board_config.get("build.arduino.ldscript", "")
        or board_config.get("build.ldscript", "")
    )
    if ldscript == "nrf52840_s140_v6.ld":
        return "0x26000"

    return "0x27000"


class Protocol:
    """One takeover upload protocol as registered in PROTOCOLS.

    ``handles``   (protocol, board, env) -> bool — must a build using
                  this protocol be taken over at all
    ``configure`` (env, platform, board, protocol) — pre-set
                  UPLOADER/UPLOADERFLAGS/UPLOADCMD
    ``graft``     (env, board) — attach the real artifact chain after
                  the upstream script registered its upload target
                  (defaults to _graft_nothing)
    """

    def __init__(self, handles, configure, graft=None):
        self.handles = handles
        self.configure = configure
        self.graft = graft or _graft_nothing


class Takeover:
    """A registry entry bound to the concrete protocol name that
    selected it (the openocd entry serves many names: stlink,
    cmsis-dap, ...). This is the object build.py drives."""

    def __init__(self, protocol, name):
        self.protocol = protocol
        self.name = name

    def configure(self, env, platform, board):
        """Pre-set UPLOADER/UPLOADERFLAGS/UPLOADCMD; the wrapper
        rewrites UPLOAD_PROTOCOL to "custom" right after this call, so
        the upstream dispatch never inspects these protocols itself."""
        self.protocol.configure(env, platform, board, self.name)

    def graft(self, env, board):
        """Attach the real artifact chain after the upstream script
        registered its upload target."""
        self.protocol.graft(env, board)


def _always(protocol, board, env):
    return True


def _handles_jlink(protocol, board, env):
    # Takeover on bootloader (DFUBOOTHEX) builds — the upload offset
    # comes from the board's linker script, not the upstream constants
    # — or via the OpenOCD-class rule (the board's debug.tools carries
    # a jlink entry on nRF MCUs).
    if "DFUBOOTHEX" in env:
        return True
    return (protocol in board.get("debug", {}).get("tools", {})
            and board.get("build.mcu", "").startswith("nrf"))


def _handles_openocd_class(protocol, board, env):
    # OpenOCD-class takeover applies on nRF MCUs, whose flash/RRAM
    # writes need a special sequence.
    return board.get("build.mcu", "").startswith("nrf")


def _configure_nrfutil_mcumgr(env, platform, board, protocol):
    # Nordic nrfutil MCUboot serial recovery over USB CDC ACM.
    # The board must have MCUboot with serial recovery enabled and the
    # device must be in serial recovery mode (via WAIT_FOR_DFU window,
    # GPIO button press, or no-application fallback).
    # Port resolution, the 1200-bps touch and the loader-CDC wait run in
    # mcumgrupload.py (this directory), a child console process, so Ctrl+C
    # aborts every wait instantly: SCons executes actions in a worker
    # thread where CPython never raises KeyboardInterrupt on Windows (the
    # SIGINT flag is only handled on the main thread, which stays parked
    # in an uninterruptible join for the whole task), so in-process wait
    # loops cannot be interrupted at all. A child process receives the
    # console Ctrl+C event itself and dies immediately, taking nrfutil
    # with it -- the same mechanism that keeps the STM32 UF2 uploader
    # (uf2upload.py) interruptible.
    # Do not install an upload-only tool during a normal build.  Besides
    # avoiding unnecessary downloads in CI, this keeps compilation
    # isolated from the host's tool-installation state.
    from SCons.Script import COMMAND_LINE_TARGETS

    cdc = board.get("upload.cdc", {})
    app_vidpid = cdc.get("app_vidpid", "")
    loader_vidpids = cdc.get("loader_vidpids", [])
    if not app_vidpid or not loader_vidpids:
        sys.stderr.write(
            "Error: upload protocol 'nrfutil-mcumgr' requires "
            "'upload.cdc.app_vidpid' and 'upload.cdc.loader_vidpids' in "
            "boards/%s.json (see seeed-xiao-nrf54lm20b.json).\n" % board.id)
        env.Exit(1)

    nrfutil_executable = "nrfutil"
    if "upload" in COMMAND_LINE_TARGETS:
        nrfutil_executable = _ensure_nrfutil_installed(env)

    env.Replace(
        UPLOADCMD=" ".join([
            '"$PYTHONEXE"',
            '"%s"' % join(_UPLOADER_DIR, "mcumgrupload.py"),
            "--nrfutil", '"%s"' % nrfutil_executable,
            "--app-vidpid", app_vidpid,
            "--loader-vidpid", " ".join('"%s"' % v for v in loader_vidpids),
            "--port", '"${UPLOAD_PORT}"',
            "--firmware", '"$MCUBOOT_IMAGE"',
        ]),
    )


def _configure_pyocd(env, platform, board, protocol):
    _ensure_pyocd_installed(env)

    pyocd_target = board.get("upload.pyocd_target")
    if not pyocd_target:
        mcu = (board.get("build.mcu") or "").strip()

        # Best-effort mapping from board MCU name to pyOCD target name.
        # Boards can override this via `upload.pyocd_target`.
        mcu_to_pyocd_target = {
            "nrf54lm20a": "nrf54lm20a",
            # nRF54L15 uses the generic nRF54L family target in pyOCD.
            "nrf54l15": "nrf54l",
            # Most nRF52 boards use the generic nRF52 family target.
            "nrf52840": "nrf52",
        }

        if mcu in mcu_to_pyocd_target:
            pyocd_target = mcu_to_pyocd_target[mcu]
        else:
            pyocd_target = "nrf54l"
            print(
                "Warning! Unknown MCU '%s' for pyOCD; defaulting to '%s'. "
                "Set 'upload.pyocd_target' in the board JSON if needed." % (mcu, pyocd_target)
            )

    pyocd_frequency = str(board.get("upload.pyocd_frequency", 4_000_000))

    env.Replace(
        UPLOADER="$PYTHONEXE",
        UPLOADERFLAGS=[
            "-m",
            "pyocd",
            "flash",
            "--target",
            pyocd_target,
            "--frequency",
            pyocd_frequency,
        ],
        UPLOADCMD='"$UPLOADER" $UPLOADERFLAGS "$SOURCE"',
    )


def _configure_probe_rs(env, platform, board, protocol):
    upload_config = board.get("upload", {})
    probe_rs_chip = upload_config.get("probe_rs_chip")
    if not probe_rs_chip:
        mcu = (board.get("build.mcu") or "").strip()
        mcu_to_probe_rs_chip = {
            "nrf54lm20a": "nRF54LM20A",
            "nrf54l15": "nRF54L15",
        }
        probe_rs_chip = mcu_to_probe_rs_chip.get(mcu)

    if not probe_rs_chip:
        sys.stderr.write(
            "Error: Unknown MCU '%s' for probe-rs. Set 'upload.probe_rs_chip' in the board JSON.\n"
            % (board.get("build.mcu") or "")
        )
        env.Exit(1)

    probe_rs_args = [
        "download",
        "--chip",
        probe_rs_chip,
        "--protocol",
        "swd",
        "--binary-format",
        "ihex",
        "--verify",
    ]

    upload_port = env.subst("$UPLOAD_PORT")
    if upload_port:
        probe_rs_args.extend(["--probe", upload_port])

    env.Replace(
        UPLOADER="probe-rs",
        UPLOADERFLAGS=probe_rs_args,
        UPLOADCMD='"$UPLOADER" $UPLOADERFLAGS "$SOURCE"',
    )


def _configure_sam_ba(env, platform, board, protocol):
    bossac = join(platform.get_package_dir("tool-bossac-nordicnrf52") or "", "bossac")
    if system() == "Windows":
        bossac += ".exe"
    env.Replace(
        UPLOADER=bossac,
        UPLOADERFLAGS=[
            "--port", '"$UPLOAD_PORT"',
            "--write",
            "--verify",
            "--reset"
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS "$FLASH_IMAGE"'
    )

    env.Append(UPLOADERFLAGS=["--erase"])

    if board.get("upload.native_usb", False):
        env.Append(UPLOADERFLAGS=["-U"])

    upload_offset = board.get("upload.offset_address")
    if upload_offset:
        env.Append(UPLOADERFLAGS=["--offset", upload_offset])

    from SCons.Script import ARGUMENTS
    if int(ARGUMENTS.get("PIOVERBOSE", 0)):
        env.Prepend(UPLOADERFLAGS=["--info", "--debug"])


def _configure_jlink(env, platform, board, protocol):
    def _jlink_cmd_script(env, source):
        build_dir = env.subst("$BUILD_DIR")
        if not os.path.isdir(build_dir):
            os.makedirs(build_dir)
        script_path = join(build_dir, "upload.jlink")
        commands = ["h"]
        if "DFUBOOTHEX" in env:
            # the grafted _signature.bin pair: FLASH_IMAGE (set by
            # graft_artifacts) is the signed half; the plain application
            # binary lands at the bootloader offset derived from the
            # linker script
            source = env.subst("$FLASH_IMAGE")
            commands.append('loadbin "%s",%s' % (
                str(source).replace("_signature", ""),
                _get_dfu_upload_offset(env.BoardConfig())))
            commands.append('loadbin "%s",%s' % (
                source, env.get("BOOT_SETTING_ADDR")))
        else:
            commands.append('loadbin "%s",%s' % (source, env.BoardConfig().get(
                "upload.offset_address", "0x0")))

        commands.append("r")
        commands.append("q")

        with open(script_path, "w") as fp:
            fp.write("\n".join(commands))
        return script_path

    env.Replace(
        __jlink_cmd_script=_jlink_cmd_script,
        UPLOADER="JLink.exe" if system() == "Windows" else "JLinkExe",
        UPLOADERFLAGS=[
            "-device", env.BoardConfig().get("debug", {}).get("jlink_device"),
            "-speed", env.GetProjectOption("debug_speed", "4000"),
            "-if", "swd",
            "-autoconnect", "1",
            "-NoGui", "1"
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS -CommanderScript "${__jlink_cmd_script(__env__, SOURCE)}"'
    )


def _configure_openocd(env, platform, board, protocol):
    debug_tools = board.get("debug", {}).get("tools", {})
    openocd_args = [
        "-d%d" % (2 if _pio_verbose() else 1)
    ]
    openocd_args.extend(
        debug_tools.get(protocol).get("server").get("arguments", []))
    if env.GetProjectOption("debug_speed"):
        openocd_args.extend(
            ["-c", "adapter speed %s" % env.GetProjectOption("debug_speed")]
        )
    # 52840 use hex to upload
    if board.get("build.mcu") == "nrf52840":
        openocd_args.extend([
            "-c", "init; targets; halt; program {$SOURCE} verify reset; shutdown"
        ])
    # nRF54L RRAM uploads. A blank (mass-erased) chip has no vector table, so
    # the core sits in LOCKUP when OpenOCD attaches; halt it before writing
    # RRAM and verify the image afterwards. Without the verify a failed write
    # still exits 0 and PlatformIO reports a false SUCCESS. See
    # https://github.com/Seeed-Studio/platform-seeedboards/issues/69
    elif board.get("build.mcu") == "nrf54l15":
        openocd_args.extend([
            "-c", "init",
            "-c", "reset halt",
            "-c", "mww 0x5004b500 0x101; load_image {$SOURCE}",
            "-c", "verify_image {$SOURCE}",
            "-c", "reset run",
            "-c", "shutdown"
        ])
    elif board.get("build.mcu") == "nrf54lm20a":
        openocd_args.extend([
            "-c", "init",
            "-c", "reset halt",
            # nrf54lm20a-load (defined in the board OpenOCD config) sets the
            # RRAMC write-enable bit and writes the image straight into RRAM.
            "-c", "nrf54lm20a-load {$SOURCE}",
            "-c", "verify_image {$SOURCE}",
            "-c", "reset run",
            "-c", "shutdown"
        ])
    else:
        print("Warning! Uploading via OpenOCD is not yet supported for this MCU.")

    openocd_args = [
        f.replace("$PACKAGE_DIR",
                  platform.get_package_dir("tool-openocd") or "")
        for f in openocd_args
    ]
    env.Replace(
        UPLOADER="openocd",
        UPLOADERFLAGS=openocd_args,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS")


def _pio_verbose():
    from SCons.Script import ARGUMENTS
    return int(ARGUMENTS.get("PIOVERBOSE", 0))


def _graft_nothing(env, board):
    """Protocols flashing the upstream custom-branch hex default keep
    the artifact chain the upstream script already registered."""


def _graft_mcumgr_signed_image(env, board):
    """Build the MCUboot signed image and make it the upload artifact.

    env.MCUbootImage (PlatformIO core builder, enabled for normal
    builds by the zephyr framework script) signs with the board's
    header_len/flash_alignment/slot_size + signature key; it returns
    None (-> unsigned fallback) when the board declares no imgtool
    params, so non-mcuboot boards are unaffected.
    """
    elf = "$BUILD_DIR/${PROGNAME}.elf"
    unsigned_bin = env.ElfToBin(
        join("$BUILD_DIR", "zephyr", "zephyr.bin"), elf)
    signed_bin = env.MCUbootImage(
        join("$BUILD_DIR", "zephyr", "zephyr.signed.bin"),
        unsigned_bin)
    image = signed_bin if signed_bin else unsigned_bin
    _attach(env, image)
    env.Replace(MCUBOOT_IMAGE=str(image[0]))


def _graft_sam_ba_binary(env, board):
    """bossac flashes binaries: build the plain .bin and re-point the
    upload command at it."""
    elf = "$BUILD_DIR/${PROGNAME}.elf"
    bin_file = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), elf)
    _attach(env, bin_file)
    env.Replace(FLASH_IMAGE=str(bin_file[0]))


def _graft_jlink_dfu_pair(env, board):
    """Bootloader (DFUBOOTHEX) builds flash the _signature.bin pair
    (plain application at the linker-script offset, signed half at
    BOOT_SETTING_ADDR); a non-bootloader jlink takeover grafts nothing.
    """
    if "DFUBOOTHEX" not in env:
        return
    elf = "$BUILD_DIR/${PROGNAME}.elf"
    bin_file = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), elf)
    if "SignBin" in env["BUILDERS"]:
        signed = env.SignBin(join("$BUILD_DIR", "${PROGNAME}"), bin_file)
        artifact = signed
    else:
        # SignBin is only registered on adafruit-BSP builds; on the
        # mbed BSP a DFU bootloader pair uploads as a plain binary.
        artifact = bin_file
    _attach(env, artifact)
    env.Replace(FLASH_IMAGE=str(artifact[0]))


def _attach(env, artifact):
    upload_alias = env.Alias("upload")
    env.Depends(upload_alias, artifact)
    # keep plain `pio run` producing the real artifact too (the pre-
    # upstream behavior: target_firm WAS this artifact)
    env.Depends(env.Alias("buildprog"), artifact)


# The takeover registry. Exact-name entries match their key, the jlink
# entry prefix-matches ("jlink", "jlink-..."), and the openocd entry
# catches every other key of the board's debug.tools (stlink,
# cmsis-dap, ...). Everything else — the protocols the upstream
# skeleton already handles: mbed, nrfjprog, nrfutil, blackmagic —
# rides the upstream dispatch unchanged.
PROTOCOLS = {
    # Nordic nrfutil MCUboot serial recovery over USB CDC (port
    # resolution / 1200-bps touch live in mcumgrupload.py, this
    # directory)
    "nrfutil-mcumgr": Protocol(
        _always,
        _configure_nrfutil_mcumgr,
        _graft_mcumgr_signed_image),
    # official pyOCD: list/rtt/erase; LM20A flash rides OpenOCD (see
    # _ensure_pyocd_installed)
    "pyocd": Protocol(_always, _configure_pyocd),
    "probe-rs": Protocol(_always, _configure_probe_rs),
    # our bossac fork carries --verify/--offset/native-USB flags the
    # generic upstream branch lacks
    "sam-ba": Protocol(_always, _configure_sam_ba, _graft_sam_ba_binary),
    "jlink": Protocol(_handles_jlink, _configure_jlink,
                      _graft_jlink_dfu_pair),
    "openocd": Protocol(_handles_openocd_class, _configure_openocd),
}


def resolve(upload_protocol, board, env):
    """The Takeover driving this build's upload, or None to ride the
    upstream dispatch unchanged."""
    if not upload_protocol:
        return None
    if upload_protocol in PROTOCOLS:
        candidate = PROTOCOLS[upload_protocol]
    elif upload_protocol.startswith("jlink"):
        candidate = PROTOCOLS["jlink"]
    elif upload_protocol in board.get("debug", {}).get("tools", {}):
        candidate = PROTOCOLS["openocd"]
    else:
        return None
    if not candidate.handles(upload_protocol, board, env):
        return None
    return Takeover(candidate, upload_protocol)
