# SPDX-License-Identifier: Apache-2.0
# Adapted from CANnectivity app/CMakeLists.txt (Apache-2.0, H.B. Andersen).
# Optional LED / DFU / timestamp / termination app sources are NOT included
# here (those features are left off in prj.conf); copy the matching files from
# the vendored CANnectivity app/src/ and enable the Kconfig to use them.

cmake_minimum_required(VERSION 3.13.1)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})

project(cannectivity LANGUAGES C)

if(CONFIG_CANNECTIVITY_USB_VID EQUAL 0x1209)
  if(CONFIG_CANNECTIVITY_USB_PID LESS_EQUAL 0x0010)
    message(WARNING
      "CONFIG_CANNECTIVITY_USB_PID is a generic pid.codes Test PID (${CONFIG_CANNECTIVITY_USB_PID})."
      )
  endif()
endif()

target_sources(app PRIVATE
  ../src/main.c
  ../src/usb.c
)

# Static fallback for zephyr/app_version.h (the PlatformIO Zephyr build does
# not run Zephyr's app_version.h generation step). See ../include/zephyr/.
target_include_directories(app PRIVATE ../include)
