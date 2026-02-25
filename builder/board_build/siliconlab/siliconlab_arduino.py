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
"""
import os
from os import listdir
from os.path import isdir, join

from SCons.Script import DefaultEnvironment

import re

env = DefaultEnvironment()
platform = env.PioPlatform()
board = env.BoardConfig()
variant = board.get("build.variant")

env.ProcessUnFlags("-flto")
env.Append(
    CCFLAGS=["-fno-lto"],
    LINKFLAGS=["-fno-lto"]
)

FRAMEWORK_DIR = platform.get_package_dir("framework-arduino-silabs")
print("FRAMEWORK_DIR=:",FRAMEWORK_DIR)
assert isdir(FRAMEWORK_DIR)


board_core = board.get("build.core")
core_candidates = [board_core, "gecko", "silabs"]
CORE_DIR = None
for core_name in core_candidates:
    candidate = join(FRAMEWORK_DIR, "cores", core_name)
    if isdir(candidate):
        CORE_DIR = candidate
        break
print("CORE_DIR=:",CORE_DIR)
assert isdir(CORE_DIR)

VARIANT_DIR = join(FRAMEWORK_DIR, "variants", "xiao_mg24")






machine_flags = [
    "-mthumb",
    "-mcpu=%s" % board.get("build.mcu"),
]


env.Append(
    ASFLAGS=[
        "-mfloat-abi=hard",
        "-mfpu=fpv5-sp-d16",
    ],
    CCFLAGS=[
        "-mfloat-abi=hard",
        "-mfpu=fpv5-sp-d16"
    ],
    LINKFLAGS=[
        "-mfloat-abi=hard",
        "-mfpu=fpv5-sp-d16"
    ]
)



var = join(VARIANT_DIR,"matter","gecko_sdk_4.4.0","platform","common","toolchain","inc","sl_gcc_preinclude.h")
_var = join(VARIANT_DIR,"matter","config","psa_crypto_config.h")
_var_ = join(VARIANT_DIR,"matter","config","sl_mbedtls_config.h")

env.Append(


    ASFLAGS=machine_flags,
    ASPPFLAGS=[
        "-x", "assembler-with-cpp",
    ],

    CFLAGS=["-std=c11"],

    CCFLAGS=machine_flags + [
        "-c",
        "-g",
        "-w",
        "-Wall",
        "-Wextra",
        "-fno-exceptions",
        "-fdata-sections",
        "-ffunction-sections",
        "-fomit-frame-pointer",
        "-imacros",
        "sl_gcc_preinclude.h",
        "-mcmse",
        "-Wno-deprecated-declarations",
        "-Wno-maybe-uninitialized",
        "-Wno-missing-field-initializers",
        "-Wno-unused-parameter",
        "-Wno-cast-function-type",
        "-Wno-psabi",
        "-fno-strict-aliasing",
        "-fno-unwind-tables",
        "-fno-asynchronous-unwind-tables",
        "-fno-common",
        "-Wno-sign-compare",
        "--specs=nano.specs",
        "-g",
        "-Os"
    ],

    CXXFLAGS=[
        "-std=c++11",
        "-std=gnu++17",
        "-fno-rtti",

    ],

    CPPDEFINES=[
        ("F_CPU", board.get("build.f_cpu")),
        ("ARDUINO", 10607),
        "ARDUINO_ARCH_SILABS",
        ("ARDUINO_SILABS", '\"2-3-0\"'),
        "ARDUINO_XIAO_MG24",
        "ARDUINO_ARCH_SILABS",
        ("NUM_LEDS", 1),
        ("NUM_HW_SERIAL", 2),
        ("NUM_HW_SPI", 2),
        ("NUM_HW_I2C", 2),
        ("NUM_DAC_HW", 2),
        ("ARDUINO_MAIN_TASK_STACK_SIZE", 2048),
        "ARDUINO_MATTER",
        ("CHIP_CRYPTO_PLATFORM",1),
        ("IS_DEMO_LIGHT",1),
        ("NVM3_DEFAULT_MAX_OBJECT_SIZE",4092),
        ("NVM3_DEFAULT_NVM_SIZE",40960),
        ("SL_STATUS_LED",0),
        ("_WANT_REENT_SMALL",1),
        ("configNUM_THREAD_LOCAL_STORAGE_POINTERS",2),
        ("configNUM_USER_THREAD_LOCAL_STORAGE_POINTERS",0),
        ("CHIP_ADDRESS_RESOLVE_IMPL_INCLUDE_HEADER", '\\"lib/address_resolve/AddressResolve_DefaultImpl.h\\"'),
        
        ("CHIP_HAVE_CONFIG_H",1),
        ("RADIO_CONFIG_DMP_SUPPORT",1),
        ("CURRENT_TIME_NOT_IMPLEMENTED",1),
        ("MBEDTLS_USER_CONFIG_FILE",'\\"sli_psa_builtin_config.h\\"'),
        # "MBEDTLS_USER_CONFIG_FILE=<sli_psa_builtin_config.h>",
        ("OPENTHREAD_CONFIG_DETERMINISTIC_ECDSA_ENABLE",0),
        ("OPENTHREAD_CONFIG_ENABLE_BUILTIN_MBEDTLS",0),
        ("SILABS_OTA_ENABLED",1),
        ("RTT_USE_ASM",1),
        ("ENABLE_WSTK_LEDS",1),
        ("EFR32MG24B220F1536IM48",1),
        ("SL_APP_PROPERTIES",1),
        ("HARDWARE_BOARD_DEFAULT_RF_BAND_2400",1),
        ("HARDWARE_BOARD_SUPPORTS_1_RF_BAND",1),
        ("HARDWARE_BOARD_SUPPORTS_RF_BAND_2400",1),
        ("HFXO_FREQ", 39000000),
        ("SL_BOARD_NAME", '\"BRD4187C\"'),
        ("SL_BOARD_REV", '\"A01\"'),
        ("configNUM_SDK_THREAD_LOCAL_STORAGE_POINTERS",2),
        ("SL_COMPONENT_CATALOG_PRESENT",1),
        ("MBEDTLS_CONFIG_FILE",'\\"sl_mbedtls_config.h\\"'),
        # "MBEDTLS_CONFIG_FILE=<sl_mbedtls_config.h>",
        ("OPENTHREAD_CORE_CONFIG_PLATFORM_CHECK_FILE",'\\"openthread-core-efr32-config-check.h\\"'),
        # ("OPENTHREAD_CORE_CONFIG_PLATFORM_CHECK_FILE",'\"openthread-core-efr32-config-check.h\"'),
        ("OPENTHREAD_PROJECT_CORE_CONFIG_FILE",'\\"openthread-core-efr32-config.h\\"'),
        # ("OPENTHREAD_PROJECT_CORE_CONFIG_FILE",'\"openthread-core-efr32-config.h\"'),
        ("OPENTHREAD_CONFIG_FILE",'\\"sl_openthread_generic_config.h\\"'),
        # ("OPENTHREAD_CONFIG_FILE",'\"sl_openthread_generic_config.h\"'),
        ("OPENTHREAD_FTD",1),
        ("SL_OPENTHREAD_STACK_FEATURES_CONFIG_FILE",'\\"sl_openthread_features_config.h\\"'),
        # ("SL_OPENTHREAD_STACK_FEATURES_CONFIG_FILE",'\"sl_openthread_features_config.h\"'),
        ("MBEDTLS_PSA_CRYPTO_CONFIG_FILE",'\\"psa_crypto_config.h\\"'),
        # ("MBEDTLS_PSA_CRYPTO_CONFIG_FILE=<psa_crypto_config.h>"),
        ("SL_RAIL_LIB_MULTIPROTOCOL_SUPPORT",1),
        ("SL_RAIL_UTIL_PA_CONFIG_HEADER",'\\"sl_rail_util_pa_config.h\\"'),
        # ("SL_RAIL_UTIL_PA_CONFIG_HEADER=<sl_rail_util_pa_config.h>"),
        ("SLI_RADIOAES_REQUIRES_MASKING",1)
    ],

    LIBPATH=[
        join(VARIANT_DIR, "matter")
    ],



    LINKFLAGS=machine_flags + [
        "--specs=nano.specs",
        '-Wl,-Map="%s"' % os.path.join("${BUILD_DIR}", "${PROGNAME}.map"),
        "-Wl,--gc-sections",
        "-Wl,--no-warn-rwx-segments"
    ],

    LIBSOURCE_DIRS=[join(FRAMEWORK_DIR, "libraries")]

    # LIBS=["c", "gcc", "m", "stdc++", "nosys"]

)

# env.Append(
#     LINKFLAGS=[join(VARIANT_DIR, "matter", "gsdk.a")]
# )
# env.Append(
#     LIBS=[    
#           "bgcommon_efr32xg24_gcc_release", 
#           "bluetooth_controller_efr32xg24_gcc_release", 
#           "bluetooth_host_efr32xg24_gcc_release", 
#           "nvm3_CM33_gcc", 
#           "rail_multiprotocol_efr32xg24_gcc_release",
#           "sl_openthread_efr32mg2x_gcc"
#         ]
# )

# Framework requires all symbols from mbed libraries
gsdk_path = join(VARIANT_DIR,"matter","gsdk.a")
env.Prepend(_LIBFLAGS="-Wl,--whole-archive ")
env.Append(_LIBFLAGS=f" {gsdk_path} -Wl,--end-group -Wl,--start-group -Wl,--no-whole-archive -lbgapi_core -lbgcommon -lble_bgapi -lble_bgapi_gatt_server -lble_bgapi_stub_gatt_client -lble_host -lble_host_accept_list_stub -lble_host_hal_series2 -lble_host_hci -lble_system -lbondingdb_stub -llinklayer -lProvision_efr32mg24 -lrail_multiprotocol_efr32xg24_gcc_release -lsl_openthread_cm33_gcc -lstdc++ -lgcc -lc -lm -lnosys")



hex_path = join(FRAMEWORK_DIR, "bootloaders", "seeed-studio-xiao-mg24-bootloader-storage-internal-single-512k.hex")
env.Append(DFUBOOTHEX=join(hex_path))



if not board.get("build.ldscript", ""):
    # Update linker script:
    ldscript_dir = join(VARIANT_DIR, "matter","linkerfile.ld")
    # ldscript_name = "linkerfile.ld"
    # env.Append(LIBPATH=[ldscript_dir])
    env.Replace(LDSCRIPT_PATH=ldscript_dir)




env.Append(
    # Due to long path names "-iprefix" hook is required to avoid toolchain crashes
    ASFLAGS=[
        "-iprefix" + os.path.join(VARIANT_DIR, "matter"),
        "@%s" % os.path.join(VARIANT_DIR, "matter", "includes.txt")

    ],

    CCFLAGS=[
        "-iprefix" + os.path.join(VARIANT_DIR, "matter"),
        "@%s" % os.path.join(VARIANT_DIR, "matter", "includes.txt"),
        "-idirafter",
        os.path.join(CORE_DIR, "api")

    ],

    CPPPATH=[
        os.path.join(CORE_DIR),
        os.path.join(CORE_DIR, "api", "deprecated"),
        os.path.join(CORE_DIR, "api", "deprecated-avr-comp","avr")
    ],

)

#
# Target: Build Core Library
#

libs = []

if "build.variant" in board:
    variants_dir = join(
        "$PROJECT_DIR", board.get("build.variants_dir")) if board.get(
            "build.variants_dir", "") else join(FRAMEWORK_DIR, "variants")
    env.Append(
        CPPPATH=[
            join(variants_dir, board.get("build.variant"))
        ]
    )
    libs.append(env.BuildLibrary(
        join("$BUILD_DIR", "FrameworkArduinoVariant"),
        join(variants_dir, board.get("build.variant"))
    ))

libs.append(
    env.BuildLibrary(
        join("$BUILD_DIR", "FrameworkArduino"),
        join(CORE_DIR)))



env.Prepend(LIBS=libs)
