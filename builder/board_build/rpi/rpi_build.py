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
from os import makedirs, remove, environ
from os.path import isdir, join, isfile, exists
import re
import time
from shutil import copyfile
import subprocess
from platformio.proc import exec_command

from platformio.public import list_serial_ports

from SCons.Script import (ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild,
                          Builder, Default, DefaultEnvironment)

def convert_size_expression_to_int(expression):
    conversion_factors = {
        "M": 1024*1024,
        "MB": 1024*1024,
        "K": 1024,
        "KB": 1024,
        "B": 1,
        "": 1 # giving no conversion factor is factor 1.
    }
    # match <floating pointer number><conversion factor>.
    extract_regex = r'^((?:[0-9]*[.])?[0-9]+)([mkbMKB]*)$'
    res = re.findall(extract_regex, expression)
    # unparsable expression? Warning.
    if len(res) == 0:
        sys.stderr.write(
            "Error: Could not parse filesystem size expression '%s'."
            " Will treat as size = 0.\n" % str(expression))
        return 0
    # access first result
    number, factor = res[0]
    number = float(number)
    number *= conversion_factors[factor.upper()]
    return int(number)

def fetch_fs_size(env):
    # follow generation formulas from makeboards.py for Earle Philhower core
    # given the total flash size, a user can specify
    # the amount for the filesystem (0MB, 2MB, 4MB, 8MB, 16MB)
    # via board_build.filesystem_size,
    # and we will calculate the flash size and eeprom size from that.
    flash_size = board.get("upload.maximum_size")
    filesystem_size = board.get("build.filesystem_size", "0MB")
    filesystem_size_int = convert_size_expression_to_int(filesystem_size)
    # last 4K are allocated for EEPROM emulation in flash.
    # see https://github.com/earlephilhower/arduino-pico/blob/3414b73172d307e9dc901f7fee83b41112f73457/libraries/EEPROM/EEPROM.cpp#L43-L46
    eeprom_size = 4096

    maximum_sketch_size = flash_size - eeprom_size - filesystem_size_int

    print("Flash size: %.2fMB" % (flash_size / 1024.0 / 1024.0))
    print("Sketch size: %.2fMB" % (maximum_sketch_size / 1024.0 / 1024.0))
    print("Filesystem size: %.2fMB" % (filesystem_size_int / 1024.0 / 1024.0))
    # Just informational
    psram_len = convert_size_expression_to_int(str(board.get("upload.psram_length", "0")))
    print("PSRAM size: %.2fMB" % (psram_len / 1024.0 / 1024.0))

    eeprom_start = 0x10000000 + flash_size - eeprom_size
    fs_start = 0x10000000 + flash_size - eeprom_size - filesystem_size_int
    fs_end = 0x10000000 + flash_size - eeprom_size

    if maximum_sketch_size <= 0:
        sys.stderr.write(
            "Error: Filesystem too large for given flash. "
            "Can at max be flash size - 4096 bytes. "
            "Available sketch size with current "
            "config would be %d bytes.\n" % maximum_sketch_size)
        sys.stderr.flush()
        env.Exit(1)

    env["PICO_FLASH_LENGTH"] = maximum_sketch_size
    env["PICO_EEPROM_START"] = eeprom_start
    env["FS_START"] = fs_start
    env["FS_END"] = fs_end
    # LittleFS configuration parameters taken from
    # https://github.com/earlephilhower/arduino-pico-littlefs-plugin/blob/master/src/PicoLittleFS.java
    env["FS_PAGE"] = 256
    env["FS_BLOCK"] = 4096

    print("Maximium Sketch size: %d "
        "EEPROM start: %s Filesystem start: %s "
        "Filesystem end: %s" % 
        (maximum_sketch_size, hex(eeprom_start), hex(fs_start), hex(fs_end)))


def __fetch_fs_size(target, source, env):
    fetch_fs_size(env)
    return (target, source)

def get_num_rpxxxx_devs(picotool_path: str):
    # regardless of whether an RP2040 or RP2350 device is deteced, it will print "type: [..] RP2350" or "type: [..] RP2040".
    # else it will not print "type:".
    output = subprocess.run('"' + picotool_path + '" info -d', check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True).stdout
    return output.count(b"type:")

def get_serial_ports_by_serial_number(serial_number):
    serial_ports = []
    ports = list_serial_ports(as_objects=True)

    for port in ports:
        if port.serial_number == serial_number:
            serial_ports.append(port.device)

    return serial_ports

SERIAL_NUMBER_PREFIX = "SER="

def get_serial_number(port_id):
    if not port_id or not port_id.startswith(SERIAL_NUMBER_PREFIX):
        return None

    return port_id[len(SERIAL_NUMBER_PREFIX):]

def BeforeUpload(target, source, env):  # pylint: disable=W0613,W0621
    upload_options = {}
    if "BOARD" in env:
        upload_options = env.BoardConfig().get("upload", {})

    # fastpath if device is already in BOOTSEL mode. We don't need to do anything.
    upload_protocol = env.subst("$UPLOAD_PROTOCOL") or "picotool"
    if upload_protocol == "picotool" and upload_options.get("use_1200bps_touch", False) is True:
        picotool_path = join(env.PioPlatform().get_package_dir("tool-picotool-rp2040-earlephilhower") or "", "picotool")
        num_now = get_num_rpxxxx_devs(picotool_path) 
        if get_num_rpxxxx_devs(picotool_path) != 0:
            print("Already found " + str(num_now) + " device(s) RPxxxx device in BOOTSEL mode, not trying to do 1200bps reset.")
            return

    potential_serial_number = get_serial_number(env.subst("$UPLOAD_PORT"))

    if potential_serial_number:
        print("Serial number " + potential_serial_number + " specified instead of a port, will search for associated serial ports.")
        associated_ports = get_serial_ports_by_serial_number(potential_serial_number)
        print("Serial ports found for device with serial number " + potential_serial_number + ": " + ("[none]" if not associated_ports else ", ".join(associated_ports)))

        if len(associated_ports) != 1:
            print("Failed to find exactly one port associated with the given serial number. Falling back to autodetection.")
            env.AutodetectUploadPort()
        else:
            env.Replace(UPLOAD_PORT=associated_ports[0])
    else:
        env.AutodetectUploadPort()

    before_ports = list_serial_ports()

    if upload_options.get("use_1200bps_touch", False):
        picotool_path = join(env.PioPlatform().get_package_dir("tool-picotool-rp2040-earlephilhower") or "", "picotool")
        num_before = get_num_rpxxxx_devs(picotool_path)
        env.TouchSerialPort("$UPLOAD_PORT", 1200)
        # delay a tiny bit in any case
        time.sleep(0.2)
        max_wait_s = 3.0
        while max_wait_s > 0:
            if get_num_rpxxxx_devs(picotool_path) > num_before:
                print("Device rebooted into BOOTSEL mode successfully.")
                break
            time.sleep(0.25)
            max_wait_s -= 0.25
            print("No new RPxxxx device found yet, waiting..")
        if get_num_rpxxxx_devs(picotool_path) == 0:
            print("Warning: Picotool did not detect any RPxxxx devices in BOOTSEL mode. Upload might fail.")

    if upload_options.get("wait_for_upload_port", False):
        env.Replace(UPLOAD_PORT=env.WaitForNewSerialPort(before_ports))


def generate_uf2(target, source, env):
    elf_file = target[0].get_path()
    env.Execute(
        " ".join(
            [
                "picotool",
                "uf2",
                "convert",
                "-t",
                "elf",
                '"%s"' % elf_file,
                '"%s"' % elf_file.replace(".elf", ".uf2")
            ]
        )
    )


# env = DefaultEnvironment()
Import("env")
platform = env.PioPlatform()
board = env.BoardConfig()
chip = board.get("build.mcu")

toolchain_tripple = "arm-none-eabi"
if chip == "rp2350-riscv":
    toolchain_tripple = "riscv32-unknown-elf"

env.Replace(
    __fetch_fs_size=fetch_fs_size,

    AR="%s-ar" % toolchain_tripple,
    AS="%s-as" % toolchain_tripple,
    CC="%s-gcc" % toolchain_tripple,
    CXX="%s-g++" % toolchain_tripple,
    GDB="%s-gdb" % toolchain_tripple,
    OBJCOPY="%s-objcopy" % toolchain_tripple,
    RANLIB="%s-ranlib" % toolchain_tripple,
    SIZETOOL="%s-size" % toolchain_tripple,

    ARFLAGS=["rc"],

    MKFSTOOL="mklittlefs",
    PICO_FS_IMAGE_NAME=env.get("PICO_FS_IMAGE_NAME", "littlefs"),

    SIZEPROGREGEXP=r"^(?:\.text|\.data|\.rodata|\.text.align|\.ARM.exidx)\s+(\d+).*",
    SIZEDATAREGEXP=r"^(?:\.data|\.bss|\.noinit)\s+(\d+).*",
    SIZECHECKCMD="$SIZETOOL -A -d $SOURCES",
    SIZEPRINTCMD='$SIZETOOL -B -d $SOURCES',

    PROGSUFFIX=".elf"
)

# Print fancier PSRAM size output (statically known allocations)
def _format_available_bytes(value, total):
    percent_raw = float(value) / float(total)
    blocks_per_progress = 10
    used_blocks = min(
        int(round(blocks_per_progress * percent_raw)), blocks_per_progress
    )
    return "[{:{}}] {: 6.1%} (used {:d} bytes from {:d} bytes)".format(
        "=" * used_blocks, blocks_per_progress, percent_raw, value, total
    )
def _get_size_output(source):
    cmd = env.get("SIZECHECKCMD")
    if not cmd:
        return None
    if not isinstance(cmd, list):
        cmd = cmd.split()
    cmd = [arg.replace("$SOURCES", str(source[0])) for arg in cmd if arg]
    sysenv = environ.copy()
    sysenv["PATH"] = str(env["ENV"]["PATH"])
    result = exec_command(env.subst(cmd), env=sysenv)
    if result["returncode"] != 0:
        return None
    return result["out"].strip()
def _calculate_size(output, pattern):
    if not output or not pattern:
        return -1
    size = 0
    regexp = re.compile(pattern)
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        match = regexp.search(line)
        if not match:
            continue
        size += sum(int(value) for value in match.groups())
    return size
old_check = env.CheckUploadSize
def new_check_size(target, source, env):
    old_check(target, source, env)
    board = env.BoardConfig()
    psram_len = convert_size_expression_to_int(str(board.get("upload.psram_length", "0")))
    if psram_len == 0:
        return
    output = _get_size_output(source)
    used_psram = _calculate_size(output, r"^(?:\.psram)\s+(\d+).*")
    print("PSRAM: " + _format_available_bytes(used_psram, psram_len))
env.CheckUploadSize = new_check_size

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
        BinToSignedBin=Builder(
            action=env.VerboseAction(" ".join([
                '"$PYTHONEXE" "%s"' % join(
                    platform.get_package_dir("framework-arduinopico") or "",
                    "tools", "signing.py"),
                "--mode",
                "sign",
                "--privatekey",
                '"%s"' % join("$PROJECT_SRC_DIR", "private.key"),
                "--bin",
                "$SOURCES",
                "--out",
                "$TARGET"
            ]), "Building $TARGET"),
            suffix=".bin.signed"
        )
    )
)

if not env.get("PIOFRAMEWORK"):
    env.SConscript("_bare.py")

env.Append(
    BUILDERS=dict(
        DataToBin=Builder(
            action=env.VerboseAction(" ".join([
                '"$MKFSTOOL"',
                "-c", "$SOURCES",
                "-p", "$FS_PAGE",
                "-b", "$FS_BLOCK",
                "-s", "${FS_END - FS_START}",
                "$TARGET"
            ]), "Building file system image from '$SOURCES' directory to $TARGET"),
            emitter=__fetch_fs_size,
            source_factory=env.Dir,
            suffix=".bin"
        )
    )
)

is_arduino_pico_build = env.BoardConfig().get("build.core", "arduino") == "earlephilhower" and "arduino" in env.get("PIOFRAMEWORK")
if is_arduino_pico_build:
    pubkey = join(env.subst("$PROJECT_SRC_DIR"), "public.key")
    if isfile(pubkey):
        header_file =  join(env.subst("$BUILD_DIR"), "core", "Updater_Signing.h")
        env.Prepend(CCFLAGS=['-I"%s"' % join("$BUILD_DIR", "core")])
        env.Execute(" ".join([
                '"$PYTHONEXE" "%s"' % join(
                    platform.get_package_dir("framework-arduinopico"), "tools", "signing.py"),
                "--mode", "header",
                "--publickey", '"%s"' % join("$PROJECT_SRC_DIR", "public.key"),
                "--out", '"%s"' % join("$BUILD_DIR", "core", "Updater_Signing.h")
        ]))

#
# Target: Build executable and linkable firmware
#

target_elf = None
target_signed_bin = None
if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.bin")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.bin.signed")
else:
    target_elf = env.BuildProgram()
    if set(["buildfs", "uploadfs"]) & set(COMMAND_LINE_TARGETS):
        target_firm = env.DataToBin(
            join("$BUILD_DIR", "${PICO_FS_IMAGE_NAME}"), "$PROJECTDATA_DIR")
        AlwaysBuild(target_firm)
    else:
        target_firm = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
        signing_script_exists = exists(join(platform.get_package_dir("framework-arduinopico") or "",
            "tools", "signing.py"))
        if is_arduino_pico_build and signing_script_exists:
            target_signed_bin = env.BinToSignedBin(join("$BUILD_DIR", "${PROGNAME}"), target_firm)
            env.Depends(target_signed_bin, "checkprogsize")
        env.Depends(target_firm, "checkprogsize")

env.AddPlatformTarget("buildfs", target_firm, target_firm, "Build Filesystem Image")
AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog = env.Alias("buildprog", [target_firm, target_signed_bin], target_firm)

env.AddPostAction(
    target_elf, env.VerboseAction(generate_uf2, "Generating UF2 image")
)

def _update_max_upload_size(env):
    fetch_fs_size(env)
    env.BoardConfig().update("upload.maximum_size", env["PICO_FLASH_LENGTH"])

# update max upload size based on set sketch size (or raw maximum size)
if env.get("PIOMAINPROG"):
    env.AddPreAction(
        "checkprogsize",
        env.VerboseAction(
            lambda source, target, env: _update_max_upload_size(env),
            "Retrieving maximum program size $SOURCE"))

#
# Target: Print binary size
#

target_size = env.Alias(
    "size", target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE"))
AlwaysBuild(target_size)

def RebootPico(target, source, env): 
    time.sleep(0.5)
    env.Execute(
        '"%s" reboot' %
            join(platform.get_package_dir("tool-picotool-rp2040-earlephilhower") or "", "picotool")
    )
#
# Target: Upload by default .bin file
#

debug_tools = env.BoardConfig().get("debug.tools", {})
upload_protocol = env.subst("$UPLOAD_PROTOCOL") or "picotool"
upload_actions = []
upload_source = target_firm

def UploadUF2ToDisk(target, source, env):
    assert "UPLOAD_PORT" in env
    progname = env.subst("$PROGNAME")
    ext = "uf2"
    fpath = join(env.subst("$BUILD_DIR"), "%s.%s" % (progname, ext))
    if not isfile(fpath):
        print(
            "Firmware file %s not found.\n" % fpath
        )
        return
    copyfile(fpath, join(env.subst("$UPLOAD_PORT"), "%s.%s" % (progname, ext)))
    print(
        "Firmware has been successfully uploaded.\n"
    )

def TryResetPico(target, source, env):
    upload_options = {}
    if "BOARD" in env:
        upload_options = env.BoardConfig().get("upload", {})
    ports = list_serial_ports()
    if len(ports) != 0:
        last_port = ports[-1]["port"]
        if upload_options.get("use_1200bps_touch", False):
            env.TouchSerialPort(last_port, 1200)
            time.sleep(2.0)

from platformio.device.list.util import list_logical_devices
from platformio.device.finder import is_pattern_port
from fnmatch import fnmatch

def find_rpi_disk(initial_port):
    msdlabels = ("RPI-RP2")
    item:str
    for item in list_logical_devices():
        if item["path"].startswith("/net"):
            continue
        if (
            initial_port
            and is_pattern_port(initial_port)
            and not fnmatch(item["path"], initial_port)
        ):
            continue
        mbed_pages = [join(item["path"], n) for n in ("INDEX.HTM", "INFO_UF2.TXT")]
        if any(isfile(p) for p in mbed_pages):
            return item["path"]
        if item["name"] and any(l in item["name"].lower() for l in msdlabels):
            return item["path"]
    return None    

def AutodetectPicoDisk(target, source, env):
    initial_port = env.subst("$UPLOAD_PORT")
    if initial_port and not is_pattern_port(initial_port):
        print(env.subst("Using manually specified: $UPLOAD_PORT"))
        return

    if upload_protocol == "mbed":
        env.Replace(UPLOAD_PORT=find_rpi_disk(initial_port))

    if env.subst("$UPLOAD_PORT"):
        print(env.subst("Auto-detected: $UPLOAD_PORT"))
    else:
        sys.stderr.write(
            "Error: Please specify `upload_port` for environment or use "
            "global `--upload-port` option.\n"
            "For some development platforms it can be a USB flash "
            "drive (i.e. /media/<user>/<device name>)\n"
        )
        env.Exit(1)

if upload_protocol == "mbed":
    upload_actions = [
        env.VerboseAction(TryResetPico, "Trying to reset Pico into bootloader mode..."),
        env.VerboseAction(AutodetectPicoDisk, "Looking for upload disk..."),
        env.VerboseAction(UploadUF2ToDisk, "Uploading $SOURCE")
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
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS $SOURCE"
    )
    upload_source = target_elf
    upload_actions = [
        env.VerboseAction(env.AutodetectUploadPort, "Looking for BlackMagic port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")
    ]
elif upload_protocol == "espota":
    if not env.subst("$UPLOAD_PORT"):
        sys.stderr.write(
            "Error: Please specify IP address or host name of ESP device "
            "using `upload_port` for build environment or use "
            "global `--upload-port` option.\n"
            "See https://docs.platformio.org/page/platforms/"
            "espressif8266.html#over-the-air-ota-update\n")
    env.Replace(
        UPLOADER=join(
            platform.get_package_dir("framework-arduinopico") or "",
            "tools", "espota.py"),
        UPLOADERFLAGS=["--debug", "--progress", "-i", "$UPLOAD_PORT", "-p", "2040"],
        UPLOADCMD='"$PYTHONEXE" "$UPLOADER" $UPLOADERFLAGS -f $SOURCE'
    )
    if "uploadfs" in COMMAND_LINE_TARGETS:
        env.Append(UPLOADERFLAGS=["-s"])
    else:
        # check if we have a .bin.signed file available.
        # since the file may not be build yet, we try to predict that we will
        # have that file if they private signing key exists.
        if isfile(join(env.subst("$PROJECT_SRC_DIR"), "private.key")):
            sys.stdout.write("Using signed OTA update file.")
            upload_source = target_signed_bin
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]
elif upload_protocol == "picotool":
    env.Replace(
        UPLOADER=join(platform.get_package_dir("tool-picotool-rp2040-earlephilhower") or "", "picotool"),
        UPLOADERFLAGS=["-v", "-x"],
        UPLOADCMD='"$UPLOADER" load $UPLOADERFLAGS $SOURCES'
    )

    if "uploadfs" in COMMAND_LINE_TARGETS:
        env.Replace(
            UPLOADER=join(platform.get_package_dir("tool-picotool-rp2040-earlephilhower") or "", "picotool"),
            UPLOADERFLAGS=[
                "load",
                "--verify"
            ],
            UPLOADCMD='"$UPLOADER" $UPLOADERFLAGS $SOURCES --offset ${hex(FS_START)}',
        )

    upload_actions = [
        env.VerboseAction(BeforeUpload, "Looking for upload port..."),
        env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE"),
    ]

    if "uploadfs" in COMMAND_LINE_TARGETS:
        # reboot after filesystem upload
        upload_actions.append(env.VerboseAction(RebootPico, "Rebooting device..."))

    upload_source = target_elf

elif upload_protocol.startswith("jlink"):

    def _jlink_cmd_script(env, source):
        build_dir = env.subst("$BUILD_DIR")
        if not isdir(build_dir):
            makedirs(build_dir)
        script_path = join(build_dir, "upload.jlink")
        upload_addr = hex(env["FS_START"]) if "uploadfs" in COMMAND_LINE_TARGETS else board.get(
            "upload.offset_address", "0x0")
        commands = [
            "h",
            "loadbin %s, %s" % (source, upload_addr),
            "RSetType 2",
            "ResetX 200",
            "q"
        ]
        with open(script_path, "w") as fp:
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
    upload_source = env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), target_elf)

elif upload_protocol in debug_tools:
    openocd_args = [
        "-d%d" % (2 if int(ARGUMENTS.get("PIOVERBOSE", 0)) else 1)
    ]
    openocd_args.extend(
        debug_tools.get(upload_protocol).get("server").get("arguments", []))
    # always use a default speed directive of 5000khz or an otherwise configured speed
    # otherwise, flash failures were observed
    speed = env.GetProjectOption("debug_speed") or "5000"
    openocd_args.extend(
        ["-c", "adapter speed %s" % speed]
    )
    if "uploadfs" in COMMAND_LINE_TARGETS:
        # filesystem upload. use FS_START.
        openocd_args.extend([
            "-c", "program {$SOURCE} ${hex(FS_START)} verify; reset init; resume; shutdown;"
        ])
    else:
        # normal firmware upload. flash starts at 0x10000000
        openocd_args.extend([
            "-c", "program {$SOURCE} %s verify; reset init; resume; shutdown;" %
            board.get("upload.offset_address", "") 
        ])
    openocd_args = [
        f.replace("$PACKAGE_DIR", platform.get_package_dir(
            "tool-openocd-rp2040-earlephilhower") or "")
        for f in openocd_args
    ]
    env.Replace(
        UPLOADER=join(platform.get_package_dir("tool-openocd-rp2040-earlephilhower") or "", "bin", "openocd"),
        UPLOADERFLAGS=openocd_args,
        UPLOADCMD="$UPLOADER $UPLOADERFLAGS")
    if not board.get("upload").get("offset_address"):
        upload_source = target_elf
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

# custom upload tool
elif upload_protocol == "custom":
    upload_actions = [env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE")]

if not upload_actions:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

AlwaysBuild(env.Alias("upload", upload_source, upload_actions))
env.AddPlatformTarget("uploadfs", target_firm, upload_actions, "Upload Filesystem Image")
#
# Default targets
#
Default([target_buildprog, target_size])
