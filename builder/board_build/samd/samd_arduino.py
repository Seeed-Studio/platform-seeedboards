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

"""
Arduino

Arduino Wiring-based Framework allows writing cross-platform software to
control devices attached to a wide range of Arduino boards to create all
kinds of creative coding, interactive objects, spaces or physical experiences.

http://arduino.cc/en/Reference/HomePage
"""

import os
from SCons.Script import DefaultEnvironment

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()
build_mcu = env.get("BOARD_MCU", board.get("build.mcu", ""))

VENDOR_CORE = board.get("build.core", "").lower()
FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-samd-seeed")
CMSIS_DIR = platform.get_package_dir("framework-cmsis")
CMSIS_ATMEL_DIR = platform.get_package_dir("framework-cmsis-atmel")
print("FRAMEWORK_DIR is:",FRAMEWORK_DIR)
print("CMSIS_DIR is:",CMSIS_DIR)
print("CMSIS_ATMEL_DIR is:",CMSIS_ATMEL_DIR)
assert all(os.path.isdir(d) for d in (FRAMEWORK_DIR, CMSIS_DIR, CMSIS_ATMEL_DIR))

MCU_FAMILY = board.get("build.system", "samd")
assert MCU_FAMILY in ("sam", "samd")

BUILD_CORE = "arduino"

def get_variants_dir():
    if "build.variants_dir" not in board:
        return os.path.join(FRAMEWORK_DIR, "variants")

    if os.path.isabs(env.subst(board.get("build.variants_dir"))):
        return board.get("build.variants_dir", "")

    return os.path.join("$PROJECT_DIR", board.get("build.variants_dir"))

machine_flags = [
    "-mcpu=%s" % board.get("build.cpu"),
    "-mthumb",
]

env.Append(
    ASFLAGS=machine_flags,
    ASPPFLAGS=[
        "-x", "assembler-with-cpp",
    ],

    CFLAGS=[
        "-std=gnu11"
    ],

    CCFLAGS=machine_flags + [
        "-Os",  # optimize for size
        "-ffunction-sections",  # place each function in its own section
        "-fdata-sections",
        "-Wall",
        "-nostdlib",
        "--param", "max-inline-insns-single=500"
    ],

    CXXFLAGS=[
        "-fno-rtti",
        "-fno-exceptions",
        "-std=gnu++11",
        "-fno-threadsafe-statics"
    ],

    CPPDEFINES=[
        ("ARDUINO", 10805),
        ("F_CPU", "$BOARD_F_CPU"),
        "USBCON"
    ],

    LIBSOURCE_DIRS=[
        os.path.join(FRAMEWORK_DIR, "libraries")
    ],

    LINKFLAGS=machine_flags + [
        "-Os",
        "-Wl,--gc-sections",
        "-Wl,--check-sections",
        "-Wl,--unresolved-symbols=report-all",
        "-Wl,--warn-common",
        "-Wl,--warn-section-align"
    ],

    LIBS=["m"]
)


if not board.get("build.ldscript", ""):
    env.Append(
        LIBPATH=[
            os.path.join(
                get_variants_dir(),
                board.get("build.variant"),
                "linker_scripts",
                "gcc",
            )
        ]
    )
    env.Replace(LDSCRIPT_PATH=board.get("build.arduino.ldscript", ""))

if "build.usb_product" in board:
    env.Append(
        CPPDEFINES=[
            ("USB_VID", board.get("build.hwids")[0][0]),
            ("USB_PID", board.get("build.hwids")[0][1]),
            ("USB_PRODUCT", '\\"%s\\"' %
             board.get("build.usb_product", "").replace('"', "")),
            ("USB_MANUFACTURER", '\\"%s\\"' %
             board.get("vendor", "").replace('"', ""))
        ]
    )



env.Append(
    CPPDEFINES=[
        "ARDUINO_ARCH_SAMD"
    ],

    CPPPATH=[
        os.path.join(
            CMSIS_DIR,
            "CMSIS",
            os.path.join("Core", "Include") if VENDOR_CORE in ("adafruit", "seeed") else "Include",
        ),  # Adafruit and Seeed cores use CMSIS v5.4 with different folder structure
        os.path.join(CMSIS_ATMEL_DIR, "CMSIS", "Device", "ATMEL"),
        os.path.join(FRAMEWORK_DIR, "cores", BUILD_CORE)
    ],

    LIBPATH=[
        os.path.join(CMSIS_DIR, "CMSIS", "Lib", "GCC"),
    ],

    LINKFLAGS=[
        "--specs=nosys.specs",
        "--specs=nano.specs"
    ],

    LIBS=["arm_cortexM0l_math"]
)


# USB-specific flags

env.Append(
    CPPDEFINES=[
        ("USB_CONFIG_POWER", board.get("build.usb_power", 100))
    ],

    CCFLAGS=[
        "-Wno-expansion-to-defined"
    ],

    CPPPATH=[
        os.path.join(FRAMEWORK_DIR, "cores", BUILD_CORE, "TinyUSB"),
        os.path.join(
            FRAMEWORK_DIR,
            "cores",
            BUILD_CORE,
            "TinyUSB",
            "Adafruit_TinyUSB_ArduinoCore",
        ),
        os.path.join(
            FRAMEWORK_DIR,
            "cores",
            BUILD_CORE,
            "TinyUSB",
            "Adafruit_TinyUSB_ArduinoCore",
            "tinyusb",
            "src",
        ),
    ]
)

env.Append(CPPPATH=[os.path.join(CMSIS_DIR, "CMSIS", "DSP", "Include")])
env.Append(
    LINKFLAGS=[
        "-Wl,--wrap,_write",
        "-u", "__wrap__write"
    ]
)


#
# Target: Build Core Library
#

libs = []

libs.append(env.BuildLibrary(
    os.path.join("$BUILD_DIR", "FrameworkArduino"),
    os.path.join(FRAMEWORK_DIR, "cores", BUILD_CORE)
))

if "build.variant" in board:
    variants_dir = get_variants_dir()

    env.Append(
        CPPPATH=[os.path.join(variants_dir, board.get("build.variant"))]
    )
    libs.append(env.BuildLibrary(
        os.path.join("$BUILD_DIR", "FrameworkArduinoVariant"),
        os.path.join(variants_dir, board.get("build.variant"))
    ))

env.Prepend(LIBS=libs)
