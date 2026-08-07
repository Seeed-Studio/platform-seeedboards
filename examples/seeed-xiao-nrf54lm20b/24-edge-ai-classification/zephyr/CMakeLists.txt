# SPDX-License-Identifier: Apache-2.0
#
# XIAO nRF54LM20B Edge AI — parcel-state classification (Axon NPU).
# Reuses Nordic's official classification sample from the sdk-edge-ai module.

cmake_minimum_required(VERSION 3.20.0)

# The sdk-edge-ai module root. The platform builder exports it as
# XIAO_EDGE_AI_DIR; allow a manual override for non-PIO builds.
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

set(EDGE_AI_CLASSIFICATION_DIR
    "${EDGE_AI_DIR}/samples/nrf_edgeai/classification"
    CACHE PATH "Official nRF Edge AI classification sample")

if(NOT EXISTS "${EDGE_AI_CLASSIFICATION_DIR}/src/main.c")
  message(FATAL_ERROR
    "EDGE_AI_CLASSIFICATION_DIR must point to the official classification sample: "
    "${EDGE_AI_CLASSIFICATION_DIR}")
endif()

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_nrf54lm20b_edgeai_classification)

set(AXON_MODEL_DIR "${EDGE_AI_CLASSIFICATION_DIR}/src/nrf_edgeai_generated/Axon")

target_include_directories(app PRIVATE "${AXON_MODEL_DIR}")

# PlatformIO compiles PROJECT_DIR/src/*.c (here: status_blink.c) itself via its
# own glob, so only the *external* official sources are added to the app target
# (with board_build.zephyr.app_build_control = true in platformio.ini). The
# generated Axon model header uses C11 static_assert, so force-include <assert.h>
# (newlib defines `static_assert` under -std=c17) before any source sees it.
target_compile_options(app PRIVATE "-include" "assert.h")
target_sources(app PRIVATE
  "${EDGE_AI_CLASSIFICATION_DIR}/src/main.c"
  "${AXON_MODEL_DIR}/nrf_edgeai_user_model.c"
)
