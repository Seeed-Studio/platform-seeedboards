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

https://github.com/arduino/ArduinoCore-renesas
"""

import os

from SCons.Script import DefaultEnvironment

from platformio import fs

# env = DefaultEnvironment()
Import("env")
platform = env.PioPlatform()
board = env.BoardConfig()


FRAMEWORK_DIR = platform.get_package_dir("framework-arduinorenesas-uno")

print("FRAMEWORK_DIR =:",FRAMEWORK_DIR)

assert os.path.isdir(FRAMEWORK_DIR)


def load_flags(filename):
    if not filename:
        return []

    file_path = os.path.join(FRAMEWORK_DIR, "variants", board.get(
        "build.variant"), "%s.txt" % filename)
    if not os.path.isfile(file_path):
        print("Warning: Couldn't find file '%s'" % file_path)
        return []

    with open(file_path, "r") as fp:
        return [f.strip() for f in fp.readlines() if f.strip()]


cflags = set(load_flags("cflags"))
cxxflags = set(load_flags("cxxflags"))
ccflags = cflags.intersection(cxxflags)

env.Append(
    ASFLAGS=[f for f in sorted(ccflags) if isinstance(f, str) and f.startswith("-m")],

    ASPPFLAGS=["-x", "assembler-with-cpp"],

    CFLAGS=sorted(list(cflags - ccflags)),

    CCFLAGS=sorted(list(ccflags)),

    CPPDEFINES=[d.replace("-D", "") for d in load_flags("defines")],

    CXXFLAGS=sorted(list(cxxflags - ccflags)),

    LIBPATH=[
        os.path.join(FRAMEWORK_DIR, "variants", board.get("build.variant")),
        os.path.join(FRAMEWORK_DIR, "variants", board.get("build.variant"), "libs")
    ],

    LINKFLAGS=[
        "-mcpu=%s" % board.get("build.cpu"),
        "-mthumb",
        "-Wl,--gc-sections",
        "--specs=nosys.specs",
        '-Wl,-Map="%s"' % os.path.join("${BUILD_DIR}", "${PROGNAME}.map")
    ],

    LIBSOURCE_DIRS=[os.path.join(FRAMEWORK_DIR, "libraries")],

    LIBS=["fsp", "stdc++", "supc++", "m", "c", "gcc", "nosys"]
)

env.Append(
    ASFLAGS=[
        "-Os",
        "-fsigned-char",
        "-ffunction-sections",
        "-fdata-sections"
    ],

    CFLAGS=[
        "-std=gnu11"
    ],

    # Due to long path names "-iprefix" hook is required to avoid toolchain crashes
    CCFLAGS=[
        "-Os",
        # Remove the 'to_unix_path' call when PIO Core v6.1.10 is released
        "-iprefix" + fs.to_unix_path(FRAMEWORK_DIR),
        "@%s" % fs.to_unix_path(os.path.join(FRAMEWORK_DIR, "variants", board.get(
            "build.variant"), "includes.txt")),
        "-w",
        "-fno-builtin"
    ],

    CPPDEFINES=[
        ("ARDUINO", 10810),
        "ARDUINO_ARCH_RENESAS",
        "ARDUINO_FSP",
        ("_XOPEN_SOURCE", 700),
        ("F_CPU", "$BOARD_F_CPU")
    ],

    CXXFLAGS=[
        "-std=gnu++17",
        "-fno-rtti",
        "-fno-exceptions",
        "-fno-use-cxa-atexit"
    ],

    CPPPATH=[
        os.path.join(FRAMEWORK_DIR, "cores", board.get("build.core"), "tinyusb"),
        os.path.join(FRAMEWORK_DIR, "cores", board.get("build.core")),
        os.path.join(FRAMEWORK_DIR, "cores", board.get(
            "build.core"), "api", "deprecated"),
        os.path.join(FRAMEWORK_DIR, "cores", board.get(
            "build.core"), "api", "deprecated-avr-comp")
    ]
)

#
# Add FPU flags
#

env.Append(
    LINKFLAGS=[
        "-mfloat-abi=hard",
        "-mfpu=fpv%s-sp-d16" % ("5" if board.id == "portenta_c33" else "4"),
    ]
)

if board.id != "portenta_c33":
    env.Append(
        LINKFLAGS=[
            "--specs=nano.specs",
        ]
    )

#
# Add Linker scripts
#

if not board.get("build.ldscript", ""):
    env.Replace(
        LDSCRIPT_PATH=os.path.join(
            FRAMEWORK_DIR, "variants",
            board.get("build.variant"),
            board.get("build.arduino.ldscript")
        )
    )

libs = []

if "build.variant" in board:
    env.Append(CPPPATH=[
        os.path.join(FRAMEWORK_DIR, "variants", board.get("build.variant"))
    ])

    libs.append(
        env.BuildLibrary(
            os.path.join("$BUILD_DIR", "FrameworkArduinoVariant"),
            os.path.join(FRAMEWORK_DIR, "variants", board.get("build.variant"))))

libs.append(
    env.BuildLibrary(
        os.path.join("$BUILD_DIR", "FrameworkArduino"),
        os.path.join(FRAMEWORK_DIR, "cores", board.get("build.core"))))

env.Prepend(LIBS=libs)
