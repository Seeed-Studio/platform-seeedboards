# SPDX-License-Identifier: Apache-2.0
set(BOARD_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../zephyr")

cmake_minimum_required(VERSION 3.13.1)
include($ENV{ZEPHYR_BASE}/cmake/app/boilerplate.cmake NO_POLICY_SCOPE)
project(blinky)

target_sources(app PRIVATE ../src/main.c)