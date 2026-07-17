import sys
import time
from os.path import join

from SCons.Script import ARGUMENTS, COMMAND_LINE_TARGETS, AlwaysBuild, Builder, Default, DefaultEnvironment


env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()
zephyr_package_name = platform.get_zephyr_package_name(board.id)

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
                '--family-id ${UF2_FAMILY_ID} -o $TARGET'
                % join(platform.get_dir(), "builder", "tools", "uf2conv.py"),
                "Building $TARGET",
            ),
            suffix=".uf2",
        ),
    }
)

upload_protocol = env.subst("$UPLOAD_PROTOCOL")
if not env.get("PIOFRAMEWORK"):
    env.SConscript("frameworks/_bare.py")

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

if "nobuild" in COMMAND_LINE_TARGETS:
    target_elf = join("$BUILD_DIR", "${PROGNAME}.elf")
    target_firm = join("$BUILD_DIR", "${PROGNAME}.hex")
else:
    target_elf = env.BuildProgram()
    target_firm = env.ElfToHex(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    env.Depends(target_firm, "checkprogsize")

AlwaysBuild(env.Alias("nobuild", target_firm))
target_buildprog_sources = [target_firm]
target_size = env.AddPlatformTarget(
    "size",
    target_elf,
    env.VerboseAction("$SIZEPRINTCMD", "Calculating size $SOURCE"),
    "Program Size",
    "Calculate program size",
)

debug_tools = board.get("debug.tools", {})
uf2_config = board.get("upload.uf2", {})
if uf2_config or "uf2" in board.get("upload.protocols", []):
    env.Replace(
        UF2_BASE_ADDR=str(board.get("upload.offset_address", "0x08008000")),
        UF2_FAMILY_ID=str(uf2_config.get("family_id", "0x00C5C5C5")),
    )
    target_bin = env.ElfToBin(join("$BUILD_DIR", "${PROGNAME}"), target_elf)
    target_uf2 = env.BinToUf2(join("$BUILD_DIR", "${PROGNAME}"), target_bin)
    env.AddPlatformTarget(
        "uf2", target_uf2, [], "Build UF2 Image", "Build UF2 image for UF2 bootloader upload"
    )
    target_buildprog_sources.append(target_uf2)
else:
    target_uf2 = None

target_buildprog = env.Alias("buildprog", target_buildprog_sources)

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
elif upload_protocol in debug_tools:
    openocd_args = ["-d%d" % (2 if int(ARGUMENTS.get("PIOVERBOSE", 0)) else 1)]
    openocd_args.extend(debug_tools[upload_protocol]["server"]["arguments"])
    openocd_args.extend(["-c", "init; reset halt; program {$SOURCE} verify reset exit; shutdown"])
    openocd_args = [
        argument.replace("$PACKAGE_DIR", platform.get_package_dir("tool-openocd") or "")
        for argument in openocd_args
    ]
    env.Replace(UPLOADER="openocd", UPLOADERFLAGS=openocd_args, UPLOADCMD="$UPLOADER $UPLOADERFLAGS")
    env.AddPlatformTarget(
        "upload", target_firm, env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE"), "Upload"
    )
elif upload_protocol == "custom":
    env.AddPlatformTarget(
        "upload", target_firm, env.VerboseAction("$UPLOADCMD", "Uploading $SOURCE"), "Upload"
    )
else:
    sys.stderr.write("Warning! Unknown upload protocol %s\n" % upload_protocol)

Default([target_buildprog, target_size])
