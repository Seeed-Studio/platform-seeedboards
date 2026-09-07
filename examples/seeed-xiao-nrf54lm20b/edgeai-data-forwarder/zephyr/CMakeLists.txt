# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#
# XIAO nRF54LM20B adapter for Nordic's official Edge AI Data Forwarder.

cmake_minimum_required(VERSION 3.20.0)

set(OFFICIAL_DF_DIR "${CMAKE_CURRENT_SOURCE_DIR}/..")

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_nrf54lm20b_edgeai_data_forwarder)

target_include_directories(app PRIVATE
  "${OFFICIAL_DF_DIR}/src"
  "${CMAKE_CURRENT_SOURCE_DIR}/../src")

target_sources(app PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/../src/main.c"
  "${OFFICIAL_DF_DIR}/src/protocol/protocol.c"
  "${OFFICIAL_DF_DIR}/src/transport/uart.c"
  "${CMAKE_CURRENT_SOURCE_DIR}/../src/sensor/lsm6dsl.c"
  "${CMAKE_CURRENT_SOURCE_DIR}/../src/protocol/data_forwarder_encode.c")
