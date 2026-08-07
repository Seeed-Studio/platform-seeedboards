# SPDX-License-Identifier: Apache-2.0
#
# XIAO nRF54LM20B Edge AI — offline person detection (Axon NPU).
# Reuses Nordic's official person_detection application from the sdk-edge-ai module.

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

set(EDGE_AI_PERSON_DETECTION_DIR
    "${EDGE_AI_DIR}/applications/person_detection"
    CACHE PATH "Official nRF Edge AI person_detection application")

if(NOT EXISTS "${EDGE_AI_PERSON_DETECTION_DIR}/src/generated/nrf_axon_model_person_det_.h")
  message(FATAL_ERROR
    "EDGE_AI_PERSON_DETECTION_DIR must point to the official person_detection application: "
    "${EDGE_AI_PERSON_DETECTION_DIR}")
endif()

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_nrf54lm20b_person_detection_offline)

target_include_directories(app PRIVATE
  "${EDGE_AI_PERSON_DETECTION_DIR}/src"
  "${CMAKE_CURRENT_SOURCE_DIR}/../src"
)

# PlatformIO compiles the project sources under PROJECT_DIR/src/*.c itself
# (its own glob), so only the *external* official source is added to the app
# target here (with board_build.zephyr.app_build_control = true in
# platformio.ini). Listing the local src/*.c here too would compile them twice
# and produce duplicate-definition link errors.
target_sources(app PRIVATE
  "${EDGE_AI_PERSON_DETECTION_DIR}/src/postprocessing.c"
)
