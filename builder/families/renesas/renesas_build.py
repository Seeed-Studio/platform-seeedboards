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
from platform import system
from os import makedirs
from os.path import basename, isdir, join

from platformio.public import list_serial_ports

from SCons.Script import (
    COMMAND_LINE_TARGETS,
    AlwaysBuild,
    Builder,
    Default,
    DefaultEnvironment,
)


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


def install_pyocd():
    try:
        import pyocd
        print("pyocd is already installed")
    except ImportError:
        print("pyocd is not installed, installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyocd"])
        print("pyocd installed successfully")

def install_r7fa4m1ab():
    try:
        output = subprocess.check_output([sys.executable, "-m", "pyocd", "pack", "show"], text=True)
        if "r7fa4m1ab" not in output:
            print("r7fa4m1ab not installed, installing...")
            subprocess.check_call([sys.executable, "-m", "pyocd", "pack", "install", "r7fa4m1ab"])
            print("r7fa4m1ab installed successfully")
        else:
            print("r7fa4m1ab is already installed")
    except subprocess.CalledProcessError as e:
        print(f"Error installing r7fa4m1ab: {e}")
        print(f"Return code: {e.returncode}")
        print(f"Output: {e.output.decode() if e.output else 'None'}")
        print(f"Error: {e.stderr.decode() if e.stderr else 'None'}")
        sys.exit(1)


# env = DefaultEnvironment()
Import("env")
platform = env.PioPlatform()
board = env.BoardConfig()

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

# Allow user to override via pre:script
if env.get("PROGNAME", "program") == "program":
    env.Replace(PROGNAME="firmware")

env.Append(
    BUILDERS=dict(
        ElfToBin=Builder(
            action=env.VerboseAction(
                " ".join(["$OBJCOPY", "-O", "binary", "$SOURCES", "$TARGET"]),
                "Building $TARGET",
            ),
            suffix=".bin",
        ),
        ElfToHex=Builder(
            action=env.VerboseAction(
                " ".join(
                    ["$OBJCOPY", "-O", "ihex", "-R", ".eeprom", "$SOURCES", "$TARGET"]
                ),
                "Building $TARGET",
            ),
            suffix=".hex",
        ),
    )
)

if not env.get("PIOFRAMEWORK"):
    env.SConscript("_bare.py")

#
# Target: Build executable and linkable firmware
#
upload_protocol = env.subst("$UPLOAD_PROTOCOL") or "picotool"
target_elf = None
if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.bin")
else:
    target_elf = env.BuildProgram()
    if upload_protocol == "pyocd":
        target_firm = env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    else:
        target_firm = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    env.Depends(target_firm, "checkprogsize")

AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog = env.Alias("buildprog", target_firm, target_firm)

#
# Target: Print binary size
#

target_size = env.Alias(
    "size", target_elf, env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE")
)
AlwaysBuild(target_size)

#
# Target: Upload by default .bin file
#

debug_tools = env.BoardConfig().get("debug.tools", {})
upload_actions = []
upload_source = target_firm

if upload_protocol == "mbed":
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, "Looking for upload disk..."),
        env.VerboseAction(env.UploadToDisk, "Uploading $SOURCE"),
    ]
elif upload_protocol == "dfu":
    hwids = board.get("build.hwids", [["0x0483", "0xDF11"]])
    vid = hwids[0][0]
    pid = hwids[0][1]

    # default tool for all boards with embedded DFU bootloader over USB
    _upload_tool = '"%s"' % join(
        platform.get_package_dir("tool-dfuutil-arduino") or "", "dfu-util"
    )
    _upload_flags = [
        "-d",
        ",".join(["%s:%s" % (hwid[0], hwid[1]) for hwid in hwids]),
        "-a",
        "0",
        "-Q",
        "-D"
    ]

    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

    env.Replace(
        UPLOADER=_upload_tool,
        UPLOADERFLAGS=_upload_flags,
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS "${SOURCE.get_abspath()}"',
    )

    upload_source = target_firm

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
        env.Append(UPLOADERFLAGS=["--usb-port"])

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
        commands = [
            "h",
            "loadbin %s, %s" % (source, board.get("upload.offset_address", "0x0")),
            "r",
            "q",
        ]
        with open(script_path, "w") as fp:
            fp.write("\n".join(commands))
        return script_path

    env.Replace(
        __jlink_cmd_script=_jlink_cmd_script,
        UPLOADER="JLink.exe" if system() == "Windows" else "JLinkExe",
        UPLOADERFLAGS=[
            "-device",
            board.get("debug", {}).get("jlink_device"),
            "-speed",
            env.GetProjectOption("debug_speed", "4000"),
            "-if",
            ("jtag" if upload_protocol == "jlink-jtag" else "swd"),
            "-autoconnect",
            "1",
            "-NoGui",
            "1",
        ],
        UPLOADCMD='$UPLOADER $UPLOADERFLAGS -CommanderScript "${__jlink_cmd_script(__env__, SOURCE)}"',
    )
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
    upload_source = env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), target_elf)

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
    openocd_args.extend([
        "-c", "program {$SOURCE} %s verify reset; shutdown;" %
            board.get("upload.offset_address", "")
    ])
    openocd_args = [
        f.replace("$PACKAGE_DIR", platform.get_package_dir(
            "tool-openocd") or "")
        for f in openocd_args
    ]
    env.Replace(
        UPLOADER="openocd",
        UPLOADERFLAGS=openocd_args,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS")

    if not board.get("upload").get("offset_address"):
        upload_source = target_elf

    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# pyocd
# If you want to use this protocol to upload the program
# please ensure that you have installed pyocd and r7fa4m1ab.
# Refer to the following installation method:
#   pip install pyocd
#   pyocd pack install r7fa4m1ab
elif upload_protocol == "pyocd":
    install_pyocd()
    install_r7fa4m1ab()
    pyocd_args = [
        "flash",
        "-e",
        "sector",
        "-a",
        "0x0",
        "-t",
        "r7fa4m1ab",
        "$SOURCE"
    ]
    env.Replace(
        UPLOADER="pyocd",
        UPLOADERFLAGS=pyocd_args,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS")
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

if not upload_actions:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

AlwaysBuild(env.Alias("upload", upload_source, upload_actions))

#
# Default targets
#

Default([target_buildprog, target_size])
