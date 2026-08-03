# SPDX-License-Identifier: LicenseRef-Nordic-5-Clause
#
# XIAO nRF54LM20B Edge AI — wakeword + keyword spotting (LOCAL, no Bluetooth).
# Self-contained sample. Sources live under PROJECT_DIR/src including the ww/ and
# kws/ subdirectories. PlatformIO's default project source glob is NOT recursive,
# so we GLOB_RECURSE here to feed every .c into the Zephyr `app` library. With
# app_build_control left at its default (false), PlatformIO compiles these app
# sources once (no separate glob -> no duplicates).

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_nrf54lm20b_wake_words_local)

target_include_directories(app PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/../src"
  "${CMAKE_CURRENT_SOURCE_DIR}/../src/ww"
  "${CMAKE_CURRENT_SOURCE_DIR}/../src/kws"
)

FILE(GLOB_RECURSE app_sources CONFIGURE_DEPENDS "../src/*.c")
target_sources(app PRIVATE ${app_sources})
