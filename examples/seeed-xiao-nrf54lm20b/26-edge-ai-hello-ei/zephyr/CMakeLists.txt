# SPDX-License-Identifier: Apache-2.0
#
# XIAO nRF54LM20B Edge AI — hello Edge Impulse (Axon NPU, C++).
# Reuses Nordic's official edge_impulse/hello_ei sample from the sdk-edge-ai
# module and the Edge Impulse model archive shipped inside it.

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

set(EDGE_AI_HELLO_EI_DIR
    "${EDGE_AI_DIR}/samples/edge_impulse/hello_ei"
    CACHE PATH "Official Edge AI hello_ei sample")

set(EDGE_IMPULSE_MODEL_ZIP
    "${EDGE_AI_HELLO_EI_DIR}/ei_model_nrf_accel_sim_axon_v54.zip"
    CACHE FILEPATH "Axon-accelerated Edge Impulse model archive")

if(NOT EXISTS "${EDGE_AI_HELLO_EI_DIR}/src/main.c")
  message(FATAL_ERROR
    "EDGE_AI_HELLO_EI_DIR must point to the official hello_ei sample: "
    "${EDGE_AI_HELLO_EI_DIR}")
endif()
if(NOT EXISTS "${EDGE_IMPULSE_MODEL_ZIP}")
  message(FATAL_ERROR "Edge Impulse model archive not found: ${EDGE_IMPULSE_MODEL_ZIP}")
endif()

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_nrf54lm20b_hello_edge_impulse)

# Only the external official main.c is added to the app target; status_blink.c
# (under PROJECT_DIR/src) is compiled by PlatformIO's own source glob.
target_sources(app PRIVATE
  "${EDGE_AI_HELLO_EI_DIR}/src/main.c"
)
target_include_directories(app PRIVATE "${EDGE_AI_HELLO_EI_DIR}/src/include")

# C linkage for the Edge Impulse module (called from C) + silence its warnings.
zephyr_compile_definitions(
  EI_C_LINKAGE=1
  EIDSP_SIGNAL_C_FN_POINTER=1
)
zephyr_compile_options(
  -Wno-double-promotion
  -Wno-unused
  -Wno-sign-compare
  -Wno-maybe-uninitialized
)
# The framework's cmsis_6 references bare CMSIS intrinsics (__sxtb16/__sxtab16)
# that GCC only exposes in C, not C++. Force-include a shim that defines them
# as inline-asm under __cplusplus so the Edge Impulse SDK's C++ units compile.
zephyr_compile_options(
  "-include" "${CMAKE_CURRENT_SOURCE_DIR}/_cmsis_cpp_shim.h"
)

# Pull the Edge Impulse model archive (shipped inside the official sample) and
# wire it up. Path is derived from the sdk-edge-ai module root, so it is portable.
include(FetchContent)
FetchContent_Declare(edge_impulse URL "${EDGE_IMPULSE_MODEL_ZIP}")
FetchContent_MakeAvailable(edge_impulse)

if(CONFIG_NRF_AXON)
  zephyr_compile_definitions(NRF_AXON_MODEL_NAME=${CONFIG_NRF_AXON_MODEL_NAME})
  zephyr_include_directories(${edge_impulse_SOURCE_DIR})
  zephyr_include_directories(${edge_impulse_SOURCE_DIR}/nordic-axon-model)
endif()
