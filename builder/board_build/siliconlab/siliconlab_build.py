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
from platform import system
from os import makedirs
from os.path import isdir, join
import os
import subprocess

IS_WINDOWS = sys.platform.startswith("win")

from SCons.Script import (COMMAND_LINE_TARGETS, AlwaysBuild, Builder, Default,
                          DefaultEnvironment)

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()


FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-silabs")
VARIANT_DIR = join(FRAMEWORK_DIR, "variants", "xiao_mg24")
TOOL_CHAIN_DIR = platform.get_package_dir("toolchain-gccarmnoneeabi")
TOOL_CHAIN_BIN_DIR = join(TOOL_CHAIN_DIR, "bin")
board_core = board.get("build.core", "silabs")
core_candidates = [board_core, "gecko", "silabs"]
CORE_DIR = None
for core_name in core_candidates:
    candidate = join(FRAMEWORK_DIR, "cores", core_name)
    if isdir(candidate):
        CORE_DIR = candidate
        break
assert isdir(CORE_DIR)

# Generate includes.txt
def generate_includes_file(root_dir, output_file="includes.txt", prefix="-iwithprefixbefore"):
    output_path = os.path.join(root_dir, output_file)
    with open(output_path, "w", encoding="utf-8") as f:
        for dirpath, dirnames, _ in os.walk(root_dir):
            rel_path = os.path.relpath(dirpath, root_dir).replace("\\", "/")  # Calculate relative paths and convert to Unix style
            if (
                rel_path.endswith("openthread/include/openthread/platform")
                or rel_path.endswith("include/openthread/platform")
                or rel_path.endswith("include/flatbuffers")
                or rel_path.endswith("matter_2.2.0/src/app")
            ):
                continue  # Skip this path  Because time.h here conflicts
            f.write(f"{prefix}/{rel_path}\n")

generate_includes_file(join(VARIANT_DIR,"matter"))

# Enable case sensitivity
def set_case_sensitivity(directory):
    try:
        result = subprocess.run(
            ["fsutil", "file", "setCaseSensitiveInfo", directory, "enable"],
            capture_output=True, text=True, shell=True
        )
        if result.returncode == 0:
            print(f"成功启用 {directory} 的大小写敏感模式")
        else:
            print(f"设置失败: {result.stderr}")
    except Exception as e:
        print(f"发生错误: {e}")

if IS_WINDOWS and isdir(join(CORE_DIR, "api")):
    set_case_sensitivity(join(CORE_DIR,"api"))

env.Replace(
    AR=join(TOOL_CHAIN_BIN_DIR, "arm-none-eabi-ar"),
    AS=join(TOOL_CHAIN_BIN_DIR, "arm-none-eabi-as"),
    CC=join(TOOL_CHAIN_BIN_DIR, "arm-none-eabi-gcc"),
    CXX=join(TOOL_CHAIN_BIN_DIR, "arm-none-eabi-g++"),
    GDB=join(TOOL_CHAIN_BIN_DIR, "arm-none-eabi-gdb"),
    OBJCOPY=join(TOOL_CHAIN_BIN_DIR, "arm-none-eabi-objcopy"),
    RANLIB=join(TOOL_CHAIN_BIN_DIR, "arm-none-eabi-ranlib"),
    SIZETOOL=join(TOOL_CHAIN_BIN_DIR, "arm-none-eabi-size"),

    ARFLAGS=["rc"],

    SIZEPROGREGEXP=r"^(?:\.text|\.data|\.rodata|\.text.align|\.ARM.exidx)\s+(\d+).*",
    SIZEDATAREGEXP=r"^(?:\.data|\.bss|\.noinit)\s+(\d+).*",
    SIZECHECKCMD="$SIZETOOL -A -d $SOURCES",
    SIZEPRINTCMD='$SIZETOOL -B -d $SOURCES',

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
        )
    )
)

if not env.get("PIOFRAMEWORK"):
    env.SConscript("_bare.py")

#
# Target: Build executable and linkable firmware
#

if "zephyr" in env.get("PIOFRAMEWORK", []):
    env.SConscript(
        join(platform.get_package_dir(
            "framework-zephyr"), "scripts", "platformio", "platformio-build-pre.py"),
        exports={"env": env}
    )

target_elf = None
if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.bin")
else:
    target_elf = env.BuildProgram()
    target_firm = env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    env.Depends(target_firm, "checkprogsize")

AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog = env.Alias("buildprog", target_firm, target_firm)

#
# Target: Print binary size
#

target_size = env.Alias(
    "size", target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE"))
AlwaysBuild(target_size)

#
# Target: Upload by default .bin file
#

upload_protocol = env.subst("$UPLOAD_PROTOCOL")
debug_tools = env.BoardConfig().get("debug.tools", {})
print("debug_tools=",debug_tools)
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

elif upload_protocol.startswith("jlink"):

    def _jlink_cmd_script(env, source):
        build_dir = env.subst("$BUILD_DIR")
        if not isdir(build_dir):
            makedirs(build_dir)
        script_path = join(build_dir, "upload.jlink")
        commands = [
            "h",
            "loadbin %s, %s" % (source, env.BoardConfig().get(
                "upload.offset_address", "0x0")),
            "r",
            "q"
        ]
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
elif upload_protocol in debug_tools:
    openocd_args = [
        "-d2"
    ]
    openocd_args.extend(
        debug_tools.get(upload_protocol).get("server").get("arguments", []))

    if env.GetProjectOption("debug_speed"):
        openocd_args.extend(
            ["-c", "adapter speed %s" % env.GetProjectOption("debug_speed")]
        )
    openocd_args.extend([
        "-c", "init; targets; halt; program {$SOURCE} verify reset; shutdown"
    ])
    openocd_args = [
        f.replace("$PACKAGE_DIR", platform.get_package_dir(
            "tool-openocd") or "")
        for f in openocd_args
    ]

    env.Replace(
        UPLOADER=join(platform.get_package_dir("tool-openocd") or "", "bin", "openocd"),
        UPLOADERFLAGS=openocd_args,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS")

    # if not board.get("upload").get("offset_address"):
    #     upload_source = target_elf

    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

else:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

AlwaysBuild(env.Alias("upload", target_firm, upload_actions))

#
# Default targets
#

Default([target_buildprog, target_size])
