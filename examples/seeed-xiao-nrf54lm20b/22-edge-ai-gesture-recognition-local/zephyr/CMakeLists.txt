# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#
# XIAO nRF54LM20B Edge AI — gesture recognition (LOCAL, no Bluetooth).
# Reuses Nordic's official gesture_recognition application (Axon NPU model over
# the LSM6DSL IMU) from the sdk-edge-ai module. BLE HID is removed
# (CONFIG_BLE_MODE_NONE); detected gestures are logged to the console.

cmake_minimum_required(VERSION 3.20.0)

if(NOT DEFINED EDGE_AI_DIR)
  if(DEFINED ENV{XIAO_EDGE_AI_DIR})
    set(EDGE_AI_DIR $ENV{XIAO_EDGE_AI_DIR})
  else()
    message(FATAL_ERROR
      "EDGE_AI_DIR / XIAO_EDGE_AI_DIR not set. This sample must be built via "
      "the XIAO nRF54LM20B platform (platform-seeedboards), which pulls in the "
      "sdk-edge-ai module.")
  endif()
endif()

set(EDGE_AI_GESTURE_APP_DIR
    "${EDGE_AI_DIR}/applications/gesture_recognition"
    CACHE PATH "Official nRF Edge AI gesture_recognition application")

if(NOT EXISTS "${EDGE_AI_GESTURE_APP_DIR}/src/main.c")
  message(FATAL_ERROR
    "EDGE_AI_GESTURE_APP_DIR is not a gesture_recognition application: "
    "${EDGE_AI_GESTURE_APP_DIR}")
endif()

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_nrf54lm20b_gesture_recognition_local)

set(OFFICIAL_SRC "${EDGE_AI_GESTURE_APP_DIR}/src")
# Reuse the official nRF54LM20DK Axon model, which runs on the LM20B NPU.
set(NN_SOURCE "${OFFICIAL_SRC}/nrf_edgeai_generated/nrf54lm20dk/Axon")
set(NN_PATH "${NN_SOURCE}/nrf_edgeai_user_model.c")

if(NOT EXISTS "${NN_PATH}")
  message(FATAL_ERROR "Official Axon gesture model not found: ${NN_PATH}")
endif()

target_include_directories(app PRIVATE
  ${OFFICIAL_SRC}
  ${OFFICIAL_SRC}/hw_modules
  ${OFFICIAL_SRC}/ble
  ${NN_SOURCE}
  "${CMAKE_CURRENT_SOURCE_DIR}/../src"
)

# Generated Axon model headers use C11 static_assert; newlib <assert.h> defines
# `static_assert` under -std=c17. Force-include it for the app target's sources
# (C/C++ only — target_compile_options does not touch assembly).
target_compile_options(app PRIVATE "-include" "assert.h")

# PlatformIO globs PROJECT_DIR/src/*.c (the local XIAO sources: main.c,
# at_gesture.c, button_xiao.c, imu_lsm6dsl.c), so only the EXTERNAL official
# sources are added here. BLE_MODE_NONE drops uxsm + ble/hid (HID-only);
# ble_common stays (mode-agnostic state holder queried by led code).
target_sources(app PRIVATE
  ${OFFICIAL_SRC}/inference_postprocessing.c
  ${OFFICIAL_SRC}/hw_modules/led/led.c
  ${OFFICIAL_SRC}/ble/ble_common.c
  ${NN_PATH}
)
