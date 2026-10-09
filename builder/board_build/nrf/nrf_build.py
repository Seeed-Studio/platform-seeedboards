# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import subprocess
import json
import os
import shutil
import site
import tarfile
import tempfile
from platform import machine, system
from os import makedirs
from os.path import isdir, isfile, join, basename
from urllib.request import urlretrieve

from SCons.Script import (ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild,
                          Builder, Default, DefaultEnvironment)

from platformio.public import list_serial_ports


def BeforeUpload(target, source, env):  # pylint: disable=W0613,W0621
    env.AutodetectUploadPort()

    upload_options = {}
    if "BOARD" in env:
        upload_options = env.BoardConfig().get("upload", {})

    if not bool(upload_options.get("disable_flushing", False)):
        env.FlushSerialBuffer("$UPLOAD_PORT")

    before_ports = list_serial_ports()

    if bool(upload_options.get("use_1200bps_touch", False)):
        env.TouchSerialPort("$UPLOAD_PORT", 1200)

    if bool(upload_options.get("wait_for_upload_port", False)):
        env.Replace(UPLOAD_PORT=env.WaitForNewSerialPort(before_ports))

    # use only port name for BOSSA
    if ("/" in env.subst("$UPLOAD_PORT") and
            env.subst("$UPLOAD_PROTOCOL") == "sam-ba"):
        env.Replace(UPLOAD_PORT=basename(env.subst("$UPLOAD_PORT")))


# USB CDC identities for the nrfutil-mcumgr upload path (app/loader VID:PID)
# are declared per board in the manifest's upload.cdc; the port resolution,
# 1200-bps touch and loader-CDC wait live in mcumgrupload.py in this
# directory, which runs as a child console process so Ctrl+C can interrupt
# every wait (see the nrfutil-mcumgr branch below).


env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()
variant = board.get("build.variant", "")
zephyr_package_name = board.get("build.zephyr.package", "")


def _get_dfu_upload_offset(board_config):
    upload_offset = board_config.get("upload.offset_address", None)
    if upload_offset:
        return upload_offset

    ldscript = basename(
        board_config.get("build.arduino.ldscript", "")
        or board_config.get("build.ldscript", "")
    )
    if ldscript == "nrf52840_s140_v6.ld":
        return "0x26000"

    return "0x27000"


def _ensure_pyocd_installed():
    # Official pyOCD: it has shipped the nRF54LM20A target since v0.44.0
    # (pyocd/pyOCD#1889). `pyocd flash` on nRF54LM20A still faults: the
    # builtin algorithm programs RRAM with the RRAMC write buffer
    # unconfigured (pyocd/pyOCD#2016); the fix is pending in
    # pyocd/pyOCD#2033 -- bump this pin once that ships in a release and
    # pyocd flash becomes usable. Until then the LM20A upload path uses
    # OpenOCD; pyocd serves list/rtt/erase.
    pyocd_version = "0.45.1"
    pyocd_spec = "pyocd==%s" % pyocd_version

    def _installed_pyocd_is_expected() -> bool:
        try:
            import subprocess
            python_exe = sys.executable  # Use the current Python executable
            # Version check first: the retired StarSphere fork also exposes the
            # nrf54lm20a target, so the target check alone cannot tell the two
            # apart and would silently keep the fork installed.
            version = subprocess.check_output([python_exe, "-m", "pyocd", "--version"]).decode("utf-8").strip()
            if pyocd_version not in version:
                return False
            output = subprocess.check_output([python_exe, "-m", "pyocd", "list", "--targets"]).decode("utf-8")
            return "nrf54lm20a" in output.lower()
        except (ImportError, subprocess.CalledProcessError, Exception):
            return False

    if _installed_pyocd_is_expected():
        return

    python_exe = env.subst("$PYTHONEXE")
    print("[INFO] Installing official pyOCD %s..." % pyocd_version)
    subprocess.check_call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([
        python_exe,
        "-m",
        "pip",
        "install",
        "--upgrade",
        pyocd_spec,
        "libusb",
    ])


_NRFUTIL_VERSION = "8.2.0"
_NRFUTIL_MCUMGR_VERSION = "0.9.0"
_NRFUTIL_DOWNLOAD_URL = "https://developer.nordicsemi.com/.pc-tools/nrfutil/%s-%s-%s.tar.gz"


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


def _ensure_nrfutil_installed():
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
            print("[INFO] Installing Nordic nrfutil %s (mcu-manager %s)..." %
                  (_NRFUTIL_VERSION, _NRFUTIL_MCUMGR_VERSION))
            makedirs(nrfutil_home, exist_ok=True)
            temporary_dir = tempfile.mkdtemp(prefix="nrfutil-", dir=nrfutil_home)
            try:
                core_archive = join(temporary_dir, "nrfutil-core.tar.gz")
                urlretrieve(_NRFUTIL_DOWNLOAD_URL % (
                    "nrfutil", target, _NRFUTIL_VERSION), core_archive)
                _safe_extract_tarball(core_archive, install_root)
            finally:
                shutil.rmtree(temporary_dir, ignore_errors=True)

        if system() != "Windows":
            os.chmod(executable, 0o755)

        if not isfile(marker):
            temporary_dir = tempfile.mkdtemp(prefix="nrfutil-", dir=nrfutil_home)
            try:
                mcumgr_archive = join(temporary_dir, "mcu-manager.tar.gz")
                urlretrieve(_NRFUTIL_DOWNLOAD_URL % (
                    "nrfutil-mcu-manager", target, _NRFUTIL_MCUMGR_VERSION), mcumgr_archive)
                subprocess.check_call(
                    [executable, "install", "--tarball", mcumgr_archive], env=process_env)
                with open(marker, "w", encoding="utf-8") as marker_file:
                    marker_file.write("%s\n" % _NRFUTIL_MCUMGR_VERSION)
            finally:
                shutil.rmtree(temporary_dir, ignore_errors=True)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        sys.stderr.write("Error: failed to install Nordic nrfutil: %s\n" % exc)
        env.Exit(1)

    if not _nrfutil_supports_mcumgr(executable, process_env):
        sys.stderr.write("Error: Nordic nrfutil mcu-manager installation is incomplete.\n")
        env.Exit(1)

    env["ENV"]["NRFUTIL_HOME"] = nrfutil_home
    return executable

env.Replace(
    AR="arm-none-eabi-ar",
    AS="arm-none-eabi-as",
    CC="arm-none-eabi-gcc",
    CXX="arm-none-eabi-g++",
    GDB="arm-none-eabi-gdb",
    OBJCOPY="arm-none-eabi-objcopy",
    RANLIB="arm-none-eabi-ranlib",
    SIZETOOL="arm-none-eabi-size",

    ARFLAGS=["rc"],

    SIZEPROGREGEXP=r"^(?:\.text|\.data|\.rodata|\.text.align|\.ARM.exidx)\s+(\d+).*",
    SIZEDATAREGEXP=r"^(?:\.data|\.bss|\.noinit)\s+(\d+).*",
    SIZECHECKCMD="$SIZETOOL -A -d $SOURCES",
    SIZEPRINTCMD='$SIZETOOL -B -d $SOURCES',

    ERASEFLAGS=["--eraseall", "-f", "nrf52"],
    ERASECMD="nrfjprog $ERASEFLAGS",

    PROGSUFFIX=".elf"
)

# Allow user to override via pre:script
if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

env.Append(
    BUILDERS=dict(
        ElfToBin=Builder(
            action=env.VerboseAction(" ".join([
                "$OBJCOPY",
                "-O",
                "binary",
                "$SOURCES",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".bin"
        ),
        ElfToHex=Builder(
            action=env.VerboseAction(" ".join([
                "$OBJCOPY",
                "-O",
                "ihex",
                "-R",
                ".eeprom",
                "$SOURCES",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".hex"
        ),
        MergeHex=Builder(
            action=env.VerboseAction(" ".join([
                '"%s"' % join(platform.get_package_dir("tool-sreccat") or "",
                    "srec_cat"),
                "$SOFTDEVICEHEX",
                "-intel",
                "$SOURCES",
                "-intel",
                "-o",
                "$TARGET",
                "-intel",
                "--line-length=44"
            ]), "Building $TARGET"),
            suffix=".hex"
        )
    )
)

upload_protocol = env.subst("$UPLOAD_PROTOCOL")

if "nrfutil" == upload_protocol or (
    board.get("build.bsp.name", "nrf5") == "adafruit"
    and "arduino" in env.get("PIOFRAMEWORK", [])
):
    env.Append(
        BUILDERS=dict(
            PackageDfu=Builder(
                action=env.VerboseAction(" ".join([
                    '"$PYTHONEXE"',
                    '"%s"' % join(platform.get_package_dir(
                        "tool-adafruit-nrfutil") or "", "adafruit-nrfutil.py"),
                    "dfu",
                    "genpkg",
                    "--dev-type",
                    "0x0052",
                    "--sd-req",
                    board.get("build.softdevice.sd_fwid"),
                    "--application",
                    "$SOURCES",
                    "$TARGET"
                ]), "Building $TARGET"),
                suffix=".zip"
            ),
            SignBin=Builder(
                action=env.VerboseAction(
                    " ".join(
                        [
                            '"$PYTHONEXE"',
                            '"%s"' % join(
                                platform.get_package_dir(
                                    "framework-arduinoadafruitnrf52"
                                )
                                or "",
                                "tools",
                                "pynrfbintool",
                                "pynrfbintool.py",
                            ),
                            "--signature",
                            "$TARGET",
                            "$SOURCES",
                        ]
                    ),
                    "Signing $SOURCES",
                ),
                suffix="_signature.bin",
            ),
        )
    )


if not env.get("PIOFRAMEWORK"):
    env.SConscript("frameworks/_bare.py")

#
# Target: Build executable and linkable firmware
#

if "zephyr" in env.get("PIOFRAMEWORK", []):
    env.SConscript(
        join(platform.get_package_dir(
            zephyr_package_name), "scripts", "platformio", "platformio-build-pre.py"),
        exports={"env": env}
    )

target_elf = None
if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.hex")
else:
    target_elf = env.BuildProgram()

    if "SOFTDEVICEHEX" in env:
        target_firm = env.MergeHex(
            join("$BUILD_DIR", "${PROGNAME}"),
            env.ElfToHex(join("$BUILD_DIR", "userfirmware"), target_elf))
    elif "nrfutil" == upload_protocol:
        target_firm = env.PackageDfu(
            join("$BUILD_DIR", "${PROGNAME}"),
            env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), target_elf))
    elif "nrfutil-mcumgr" == upload_protocol:
        # Produce a signed MCUboot image (zephyr.signed.bin) for USB CDC ACM
        # upload via nrfutil mcu-manager. env.MCUbootImage runs imgtool sign
        # using the board's header_len/flash_alignment/slot_size + signature
        # key; it returns None (-> unsigned fallback) when the board does not
        # declare imgtool params, so non-mcuboot boards are unaffected.
        unsigned_bin = env.ElfToBin(
            join("$BUILD_DIR", "${PROGNAME}"), target_elf)
        signed_bin = env.MCUbootImage(
            join("$BUILD_DIR", "zephyr", "zephyr.signed.bin"),
            unsigned_bin)
        target_firm = signed_bin if signed_bin else unsigned_bin
    elif "nrfjprog" == upload_protocol:
        target_firm = env.ElfToHex(
            join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    elif "sam-ba" == upload_protocol:
        target_firm = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    else:
        if "DFUBOOTHEX" in env:
            if upload_protocol == "cmsis-dap" and board.get("build.mcu") == "nrf52840":
                target_firm = env.ElfToHex(
                    join("$BUILD_DIR", "${PROGNAME}"), target_elf)
            else:
                target_firm = env.SignBin(
                    join("$BUILD_DIR", "${PROGNAME}"),
                    env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), target_elf))
        else:
            target_firm = env.ElfToHex(
                join("$BUILD_DIR", "${PROGNAME}"), target_elf)
        env.Depends(target_firm, "checkprogsize")

AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog = env.Alias("buildprog", target_firm, target_firm)

if "DFUBOOTHEX" in env:
    env.Append(
        # Check the linker script for the correct location
        BOOT_SETTING_ADDR=board.get("build.bootloader.settings_addr", "0x7F000")
    )

    env.AddPlatformTarget(
        "dfu",
        env.PackageDfu(
            join("$BUILD_DIR", "${PROGNAME}"),
            env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), target_elf),
        ),
        target_firm,
        "Generate DFU Image",
    )

    env.AddPlatformTarget(
        "bootloader",
        None,
        [
            env.VerboseAction(
                "nrfjprog --program $DFUBOOTHEX -f nrf52 --chiperase",
                "Uploading $DFUBOOTHEX",
            ),
            env.VerboseAction(
                "nrfjprog --erasepage $BOOT_SETTING_ADDR -f nrf52",
                "Erasing bootloader config",
            ),
            env.VerboseAction(
                "nrfjprog --memwr $BOOT_SETTING_ADDR --val 0x00000001 -f nrf52",
                "Disable CRC check",
            ),
            env.VerboseAction("nrfjprog --reset -f nrf52", "Reset nRF52"),
        ],
        "Burn Bootloader",
    )

if "bootloader" in COMMAND_LINE_TARGETS and "DFUBOOTHEX" not in env:
    sys.stderr.write("Error. The board is missing the bootloader binary.\n")
    env.Exit(1)

#
# Target: Print binary size
#

target_size = env.AddPlatformTarget(
    "size",
    target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE"),
    "Program Size",
    "Calculate program size",
)

#
# Target: Upload by default .bin file
#

debug_tools = env.BoardConfig().get("debug.tools", {})
upload_actions = []

if upload_protocol == "mbed":
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, "Looking for upload disk..."),
        env.VerboseAction(env.UploadToDisk, "Uploading $SOURCE")
    ]

elif upload_protocol.startswith("blackmagic"):
    env.Replace(
        UPLOADER="$GDB",
        UPLOADERFLAGS=[
            "-nx",
            "--batch",
            "-ex", "target extended-remote $UPLOAD_PORT",
            "-ex", "monitor %s_scan" %
                   ("jtag" if upload_protocol == "blackmagic-jtag" else "swdp"),
            "-ex", "attach 1",
            "-ex", "load",
            "-ex", "compare-sections",
            "-ex", "kill"
        ],
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS $BUILD_DIR/${PROGNAME}.elf"
    )
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, "Looking for BlackMagic port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
    ]

elif upload_protocol == "nrfjprog":
    env.Replace(
        UPLOADER="nrfjprog",
        UPLOADERFLAGS=[
            "--sectorerase" if "DFUBOOTHEX" in env else "--chiperase",
            "--reset"
        ],
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS --program $SOURCE"
    )
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

elif upload_protocol == "nrfutil":
    env.Replace(
        UPLOADER=join(platform.get_package_dir(
            "tool-adafruit-nrfutil") or "", "adafruit-nrfutil.py"),
        UPLOADERFLAGS=[
            "dfu",
            "serial",
            "-p",
            "$UPLOAD_PORT",
            "-b",
            "$UPLOAD_SPEED",
            "--singlebank",
        ],
        UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS -pkg $SOURCE'
    )
    upload_actions = [
        env.VerboseAction(BeforeUpload, "Looking for upload port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
    ]

elif upload_protocol == "nrfutil-mcumgr":
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
    # avoiding unnecessary downloads in CI, this keeps compilation isolated
    # from the host's tool-installation state.
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
        nrfutil_executable = _ensure_nrfutil_installed()

    env.Replace(
        UPLOADCMD=" ".join([
            '"$PYTHONEXE"',
            '"%s"' % join(platform.get_dir(), "builder", "board_build", "nrf",
                          "mcumgrupload.py"),
            "--nrfutil", '"%s"' % nrfutil_executable,
            "--app-vidpid", app_vidpid,
            "--loader-vidpid", " ".join('"%s"' % v for v in loader_vidpids),
            "--port", '"${UPLOAD_PORT}"',
            "--firmware", '"$SOURCE"',
        ]),
    )
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

elif upload_protocol == "sam-ba":
    bossac = join(platform.get_package_dir("tool-bossac") or "", "bossac")
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
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS "${SOURCE.get_abspath()}"'
    )

    env.Append(UPLOADERFLAGS=["--erase"])
    if env.BoardConfig().get("upload.native_usb", False):
        env.Append(UPLOADERFLAGS=["-U"])

    upload_offset = board.get("upload.offset_address")
    if upload_offset:
        env.Append(UPLOADERFLAGS=["--offset", upload_offset])

    if int(ARGUMENTS.get("PIOVERBOSE", 0)):
        env.Prepend(UPLOADERFLAGS=["--info", "--debug"])

    upload_actions = [
        env.VerboseAction(BeforeUpload, "Looking for upload port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
    ]

elif upload_protocol.startswith("jlink"):

    def _jlink_cmd_script(env, source):
        build_dir = env.subst("$BUILD_DIR")
        if not isdir(build_dir):
            makedirs(build_dir)
        script_path = join(build_dir, "upload.jlink")
        commands = ["h"]
        if "DFUBOOTHEX" in env:
            commands.append("loadbin %s,%s" % (str(source).replace("_signature", ""),
                _get_dfu_upload_offset(env.BoardConfig())))
            commands.append("loadbin %s,%s" % (source, env.get("BOOT_SETTING_ADDR")))
        else:
            commands.append("loadbin %s,%s" % (source, env.BoardConfig().get(
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
            "-if", ("jtag" if upload_protocol == "jlink-jtag" else "swd"),
            "-autoconnect", "1",
            "-NoGui", "1"
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS -CommanderScript "${__jlink_cmd_script(__env__, SOURCE)}"'
    )
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

elif upload_protocol == "pyocd":
    _ensure_pyocd_installed()

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
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

elif upload_protocol == "probe-rs":
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
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

elif upload_protocol in debug_tools:
    openocd_args = [
        "-d%d" % (2 if int(ARGUMENTS.get("PIOVERBOSE", 0)) else 1)
    ]
    openocd_args.extend(
        debug_tools.get(upload_protocol).get("server").get("arguments", []))
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
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

else:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

env.AddPlatformTarget("upload", target_firm, upload_actions, "Upload")


#
# Target: Erase Flash
#

env.AddPlatformTarget(
    "erase", None, env.VerboseAction("$ERASECMD", "Erasing..."), "Erase Flash")

#
# Information about obsolete method of specifying linker scripts
#

if any("-Wl,-T" in f for f in env.get("LINKFLAGS", [])):
    print("Warning! '-Wl,-T' option for specifying linker scripts is deprecated. "
          "Please use 'board_build.ldscript' option in your 'platformio.ini' file.")

#
# Default targets
#

Default([target_buildprog, target_size])
