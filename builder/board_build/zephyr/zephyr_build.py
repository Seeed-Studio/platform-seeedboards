# Zephyr family build entry — upload/target wiring for all Zephyr boards.
#
# Distilled from the predecessor repo's proven nrf_build.py and
# stm32_build.py zephyr paths (the nRF52/Arduino-only branches stay in
# the predecessor). Upload profiles covered, all manifest-driven via
# upload.protocol:
#   uf2            STM32C5 (1200-bps touch -> XIAOC5BOOT volume)
#   nrfutil-mcumgr nRF54LM20B (MCUboot signed image over USB CDC)
#   cmsis-dap/stlink/jlink/pyocd/probe-rs  SWD probes
#
# Attribution:
# Adapted from pioarduino/platform-espressif32-style PlatformIO builders
# and the Seeed platform-seeedboards predecessor:
# https://github.com/Seeed-Studio/platform-seeedboards
# Modified by Seeed Studio.

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from os import makedirs
from os.path import basename, isfile, join
from platform import machine, system
from urllib.request import urlretrieve

from SCons.Script import ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild, Builder, Default, DefaultEnvironment

from platformio.public import list_serial_ports

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()
zephyr_package_name = board.get("build.zephyr.package", "")

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
    SIZEPRINTCMD="$SIZETOOL -B -d $SOURCES",
    PROGSUFFIX=".elf",
)

if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

env.Append(
    BUILDERS={
        "ElfToBin": Builder(
            action=env.VerboseAction(
                "$OBJCOPY -O binary $SOURCES $TARGET", "Building $TARGET"
            ),
            suffix=".bin",
        ),
        "ElfToHex": Builder(
            action=env.VerboseAction(
                "$OBJCOPY -O ihex -R .eeprom $SOURCES $TARGET", "Building $TARGET"
            ),
            suffix=".hex",
        ),
        "BinToUf2": Builder(
            action=env.VerboseAction(
                '"$PYTHONEXE" "%s" -i $SOURCES -b ${UF2_BASE_ADDR} '
                "--family-id ${UF2_FAMILY_ID} -o $TARGET"
                % join(platform.get_dir(), "builder", "tools", "uf2conv.py"),
                "Building $TARGET",
            ),
            suffix=".uf2",
        ),
    }
)

upload_protocol = env.subst("$UPLOAD_PROTOCOL")

if not env.get("PIOFRAMEWORK"):
    env.SConscript("_bare.py", exports="env")

if "zephyr" in env.get("PIOFRAMEWORK", []):
    env.SConscript(
        join(
            platform.get_package_dir(zephyr_package_name),
            "scripts",
            "platformio",
            "platformio-build-pre.py",
        ),
        exports={"env": env},
    )

#
# nRF54LM20B DFU port resolution (USB CDC identities of the three-image
# layout). DFU is performed by the loader image (usb_mcumgr, slot1), NOT
# by mcuboot, so when the board is in DFU mode the *loader's* CDC is what
# enumerates.
#   APP_CDC    : the running user app (Seeed VID 0x2886, CDC_ACM_SERIAL_PID
#                0x8013, set in the framework board Kconfig).
#   LOADER_CDC : the DFU loader image (Seeed VID 0x2886, PID 0x0013, baked
#                into scripts/factory_flash/firmware/USB_DFU.hex).
#

_APP_CDC_VIDPID = "2886:8013"
_LOADER_CDC_VIDPIDS = ("2886:0013",)


def _find_port_by_vidpid(vidpid, ports=None):
    ports = ports if ports is not None else list_serial_ports()
    for p in ports:
        if vidpid in (p.get("hwid") or "").upper():
            return p.get("port")
    return None


def _find_loader_port(ports=None):
    for vidpid in _LOADER_CDC_VIDPIDS:
        port = _find_port_by_vidpid(vidpid, ports)
        if port:
            return port
    return None


def _wait_for_loader_port(timeout=60):
    for _ in range(timeout):
        port = _find_loader_port()
        if port:
            return port
        time.sleep(1)
    return None


def DfuUpload1200(target, source, env):  # pylint: disable=W0613,W0621
    """Resolve the DFU (loader) upload port for the nRF54LM20B.

    Handles every board state so a crashed/empty app never bricks the device:
      1) an explicit upload_port (--upload-port / `upload_port =`) is honored;
         its role is detected by VID:PID;
      2) the loader CDC is already present (board already in DFU via Button 0
         + reset, or via the empty-slot NO_APPLICATION auto-loader) -> use it
         directly and skip the 1200-bps touch (the anti-brick fast path);
      3) the app CDC is present (healthy app) -> touch 1200 to reboot into the
         loader, then poll for the loader CDC (matching its VID:PID only, not
         WaitForNewSerialPort's "any new port", so other USB devices cannot be
         grabbed by mistake);
      4) nothing recognized -> prompt the user to enter DFU manually and poll
         for the loader CDC.
    """
    explicit = env.subst("$UPLOAD_PORT")

    # (1) Explicit port: detect its role by VID:PID.
    if explicit:
        if explicit == _find_loader_port():
            print("Configured port %s is the DFU loader; using it directly."
                  % explicit)
            return
        # Otherwise treat it as the app port -> fall through to the touch path.
    else:
        # (2) Loader CDC already present -> board already in DFU mode.
        loader_port = _find_loader_port()
        if loader_port:
            env.Replace(UPLOAD_PORT=loader_port)
            print("Board already in DFU mode; using loader port %s."
                  % loader_port)
            return

    # (3) App CDC present -> touch 1200 -> poll for the loader CDC.
    app_port = explicit or _find_port_by_vidpid(_APP_CDC_VIDPID)
    if app_port:
        env.Replace(UPLOAD_PORT=app_port)
        print("Touching %s at 1200 baud -> DFU..." % app_port)
        env.TouchSerialPort("$UPLOAD_PORT", 1200)
        loader_port = _wait_for_loader_port(60)
        if not loader_port:
            sys.stderr.write(
                "Error: the board did not enter DFU mode after the 1200-bps "
                "touch. Hold Button 0 (P0.09) and press reset, then retry.\n")
            env.Exit(1)
        env.Replace(UPLOAD_PORT=loader_port)
        print("Loader port: %s" % env.subst("$UPLOAD_PORT"))
        return

    # (4) Nothing recognized -> prompt manual DFU and poll for the loader CDC.
    sys.stdout.write(
        "No app CDC (VID:PID=%s) found. To recover, hold Button 0 "
        "(P0.09) and press reset to enter DFU mode. Waiting for the DFU "
        "loader CDC (VID:PID=%s)...\n" % (_APP_CDC_VIDPID, _LOADER_CDC_VIDPIDS[0]))
    sys.stdout.flush()
    port = _wait_for_loader_port(60)
    if not port:
        sys.stderr.write(
            "Error: could not find the DFU port. Put the board in DFU mode "
            "(hold Button 0 / P0.09 + reset) and retry, or set the port "
            "explicitly: `upload_port = COMxx` in platformio.ini or "
            "`pio run -t upload --upload-port COMxx`.\n")
        env.Exit(1)
    env.Replace(UPLOAD_PORT=port)
    print("DFU port detected: %s" % env.subst("$UPLOAD_PORT"))


#
# Nordic nrfutil v8 (mcu-manager) installer -- downloaded only when an
# upload actually runs, never during plain builds.
#

_NRFUTIL_VERSION = "8.2.0"
_NRFUTIL_MCUMGR_VERSION = "0.9.0"
_NRFUTIL_DOWNLOAD_URL = (
    "https://developer.nordicsemi.com/.pc-tools/nrfutil/%s-%s-%s.tar.gz")


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
            if (member_path != destination
                    and not member_path.startswith(destination + os.sep)):
                raise RuntimeError("Unsafe path in nrfutil archive: %s" % member.name)
        archive.extractall(destination)


def _ensure_nrfutil_installed():
    """Return nrfutil v8 with mcu-manager without altering PlatformIO's venv.

    The legacy PyPI ``nrfutil`` package is capped at v5 and depends on Click
    7, while PlatformIO Core needs Click 8. Nordic's v8 CLI is a standalone
    executable, so keep it in PlatformIO's tool cache rather than using pip.
    """
    system_nrfutil = shutil.which("nrfutil")
    if system_nrfutil and _nrfutil_supports_mcumgr(system_nrfutil):
        return system_nrfutil

    target = _nrfutil_target()
    if not target:
        sys.stderr.write(
            "Error: automatic Nordic nrfutil installation is unsupported on "
            "%s/%s. Install nrfutil 8 with the mcu-manager command manually.\n"
            % (system(), machine()))
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
            print("[INFO] Installing Nordic nrfutil %s (mcu-manager %s)..."
                  % (_NRFUTIL_VERSION, _NRFUTIL_MCUMGR_VERSION))
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
                    "nrfutil-mcu-manager", target, _NRFUTIL_MCUMGR_VERSION),
                    mcumgr_archive)
                subprocess.check_call(
                    [executable, "install", "--tarball", mcumgr_archive],
                    env=process_env)
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


#
# Target: Build executable and linkable firmware
#

if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.hex")
else:
    target_elf = env.BuildProgram()
    if "nrfutil-mcumgr" == upload_protocol:
        # Produce a signed MCUboot image (zephyr.signed.bin) for USB CDC ACM
        # upload via nrfutil mcu-manager. env.MCUbootImage runs imgtool sign
        # using the board's header_len/flash_alignment/slot_size + signature
        # key; it is patched into the framework package's builder by
        # zephyr_framework.py and returns None (-> unsigned fallback) when the
        # board does not declare imgtool params, so non-mcuboot boards are
        # unaffected.
        unsigned_bin = env.ElfToBin(
            join("$BUILD_DIR", "${PROGNAME}"), target_elf)
        signed_bin = env.MCUbootImage(
            join("$BUILD_DIR", "zephyr", "zephyr.signed.bin"),
            unsigned_bin)
        target_firm = signed_bin if signed_bin else unsigned_bin
    else:
        target_firm = env.ElfToHex(
            join("$BUILD_DIR", "${PROGNAME}"), target_elf)
        env.Depends(target_firm, "checkprogsize")

AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog_sources = [target_firm]

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
# UF2 image (boards with a UF2 bootloader)
#

debug_tools = board.get("debug.tools", {})
uf2_config = board.get("upload.uf2", {})
target_uf2 = None
if uf2_config or "uf2" in board.get("upload.protocols", []):
    env.Replace(
        UF2_BASE_ADDR=str(board.get("upload.offset_address", "0x08008000")),
        UF2_FAMILY_ID=str(uf2_config.get("family_id", "0x00C5C5C5")),
    )
    target_bin = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    target_uf2 = env.BinToUf2(join("$BUILD_DIR", "${PROGNAME}"), target_bin)
    env.AddPlatformTarget(
        "uf2", target_uf2, [], "Build UF2 Image",
        "Build UF2 image for UF2 bootloader upload",
    )
    target_buildprog_sources.append(target_uf2)

target_buildprog = env.Alias("buildprog", target_buildprog_sources)

#
# Target: Upload
#

upload_actions = []

if upload_protocol == "uf2":
    tools_dir = join(platform.get_dir(), "builder", "tools")
    volume_label = uf2_config.get("volume_label", "XIAOC5BOOT")
    env.Replace(
        UPLOADCMD='"$PYTHONEXE" "%s" "$SOURCE" --label %s --port "${UPLOAD_PORT}"'
        % (join(tools_dir, "uf2upload.py"), volume_label),
    )

    def before_uf2_upload(target, source, env):  # pylint: disable=unused-argument
        env.AutodetectUploadPort()
        if board.get("upload.use_1200bps_touch", False):
            env.TouchSerialPort("$UPLOAD_PORT", 1200)
            time.sleep(0.5)

    env.AddPlatformTarget(
        "upload",
        target_uf2,
        [
            env.VerboseAction(before_uf2_upload, "Triggering bootloader via 1200-bps touch"),
            env.VerboseAction("$UPLOADCMD", "Uploading via UF2"),
        ],
        "Upload",
    )

elif upload_protocol == "stlink":
    env.Replace(
        UPLOADER="STM32_Programmer_CLI",
        UPLOADERFLAGS=[
            "-c", "port=swd",
            "-w", "$SOURCE", str(board.get("upload.offset_address", "0x08000000")),
            "-v", "-rst",
        ],
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS",
    )
    env.AddPlatformTarget(
        "upload", target_firm, env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE"), "Upload"
    )

elif upload_protocol == "nrfutil-mcumgr":
    # Nordic nrfutil MCUboot serial recovery over USB CDC ACM.
    # The board must have MCUboot with serial recovery enabled and the
    # device must be in serial recovery mode (via WAIT_FOR_DFU window,
    # GPIO button press, or no-application fallback).
    # Do not install an upload-only tool during a normal build. Besides
    # avoiding unnecessary downloads in CI, this keeps compilation
    # isolated from the host's tool-installation state.
    nrfutil_executable = "nrfutil"
    if "upload" in COMMAND_LINE_TARGETS:
        nrfutil_executable = _ensure_nrfutil_installed()

    env.Replace(
        UPLOADER=nrfutil_executable,
        UPLOADERFLAGS=[
            "mcu-manager",
            "serial",
            "image-upload",
            "--serial-port", '"$UPLOAD_PORT"',
            "--timeout", "120",
            "--firmware",
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS "$SOURCE"',
        RESETCMD='$UPLOADER mcu-manager serial reset --serial-port "$UPLOAD_PORT" --timeout 60'
    )
    upload_actions = [
        env.VerboseAction(DfuUpload1200, "Preparing DFU port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE"),
        env.VerboseAction("$RESETCMD", "Resetting device...")
    ]
    env.AddPlatformTarget("upload", target_firm, upload_actions, "Upload")

elif upload_protocol.startswith("jlink"):

    def _jlink_cmd_script(env, source):
        build_dir = env.subst("$BUILD_DIR")
        if not os.path.isdir(build_dir):
            makedirs(build_dir)
        script_path = join(build_dir, "upload.jlink")
        commands = [
            "h",
            "loadbin %s,%s" % (source, board.get("upload.offset_address", "0x0")),
            "r",
            "q",
        ]
        with open(script_path, "w", encoding="utf-8") as fp:
            fp.write("\n".join(commands))
        return script_path

    env.Replace(
        __jlink_cmd_script=_jlink_cmd_script,
        UPLOADER="JLink.exe" if system() == "Windows" else "JLinkExe",
        UPLOADERFLAGS=[
            "-device", board.get("debug", {}).get("jlink_device"),
            "-speed", env.GetProjectOption("debug_speed", "4000"),
            "-if", ("jtag" if upload_protocol == "jlink-jtag" else "swd"),
            "-autoconnect", "1",
            "-NoGui", "1"
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS -CommanderScript "${__jlink_cmd_script(__env__, SOURCE)}"'
    )
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
    env.AddPlatformTarget("upload", target_firm, upload_actions, "Upload")

elif upload_protocol == "pyocd":

    def _ensure_pyocd_installed():
        # Always use the forked pyOCD with nRF54LM20A support.
        import subprocess  # pylint: disable=import-outside-toplevel

        pyocd_spec = (
            "pyocd @ git+https://github.com/StarSphere-1024/pyOCD.git"
            "@lm20_stable")

        def _installed_pyocd_is_expected():
            try:
                python_exe = sys.executable
                output = subprocess.check_output(
                    [python_exe, "-m", "pyocd", "list", "--targets"],
                    stderr=subprocess.DEVNULL).decode("utf-8")
                return "nrf54lm20a" in output.lower()
            except (OSError, subprocess.CalledProcessError):
                return False

        if _installed_pyocd_is_expected():
            return

        python_exe = env.subst("$PYTHONEXE")
        print("[INFO] Installing pyOCD from fork...")
        subprocess.check_call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([
            python_exe, "-m", "pip", "install", "--upgrade", pyocd_spec, "libusb",
        ])

    _ensure_pyocd_installed()

    pyocd_target = board.get("upload.pyocd_target")
    if not pyocd_target:
        pyocd_target = "nrf54l"
        print(
            "Warning: board declares no upload.pyocd_target; defaulting to "
            "'%s'." % pyocd_target)
    pyocd_frequency = str(board.get("upload.pyocd_frequency", 4_000_000))

    env.Replace(
        UPLOADER="$PYTHONEXE",
        UPLOADERFLAGS=[
            "-m", "pyocd", "flash",
            "--target", pyocd_target,
            "--frequency", pyocd_frequency,
        ],
        UPLOADCMD='"$UPLOADER" $UPLOADERFLAGS "$SOURCE"',
    )
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
    env.AddPlatformTarget("upload", target_firm, upload_actions, "Upload")

elif upload_protocol == "probe-rs":
    upload_config = board.get("upload", {})
    probe_rs_chip = upload_config.get("probe_rs_chip")
    if not probe_rs_chip:
        sys.stderr.write(
            "Error: probe-rs upload requires upload.probe_rs_chip in the "
            "board manifest.\n")
        env.Exit(1)

    probe_rs_args = [
        "download",
        "--chip", probe_rs_chip,
        "--protocol", "swd",
        "--binary-format", "ihex",
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
    env.AddPlatformTarget("upload", target_firm, upload_actions, "Upload")

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
    mcu = board.get("build.mcu")
    if mcu == "nrf54l15":
        # nRF54L RRAM uploads. A blank (mass-erased) chip has no vector
        # table, so the core sits in LOCKUP when OpenOCD attaches; halt it
        # before writing RRAM and verify the image afterwards. Without the
        # verify a failed write still exits 0 and PlatformIO reports a
        # false SUCCESS.
        openocd_args.extend([
            "-c", "init",
            "-c", "reset halt",
            "-c", "mww 0x5004b500 0x101; load_image {$SOURCE}",
            "-c", "verify_image {$SOURCE}",
            "-c", "reset run",
            "-c", "shutdown"
        ])
    elif mcu in ("nrf54lm20a", "nrf54lm20b"):
        openocd_args.extend([
            "-c", "init",
            "-c", "reset halt",
            # nrf54lm20a-load (defined in the board OpenOCD config) sets
            # the RRAMC write-enable bit and writes the image straight
            # into RRAM.
            "-c", "nrf54lm20a-load {$SOURCE}",
            "-c", "verify_image {$SOURCE}",
            "-c", "reset run",
            "-c", "shutdown"
        ])
    else:
        openocd_args.extend([
            "-c", "init; reset halt; program {$SOURCE} verify reset exit; shutdown"
        ])

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
    env.AddPlatformTarget("upload", target_firm, upload_actions, "Upload")

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
    env.AddPlatformTarget("upload", target_firm, upload_actions, "Upload")

else:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

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
