cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(xiao_nrf54lm20b_edgeai_gesture_idle_move)

target_include_directories(app PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/../src
  ${CMAKE_CURRENT_SOURCE_DIR}/../src/nrf_edgeai_generated
)

target_compile_options(app PRIVATE "-include" "assert.h")

target_sources(app PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/../src/main.c
  ${CMAKE_CURRENT_SOURCE_DIR}/../src/imu_lsm6dsl.c
  ${CMAKE_CURRENT_SOURCE_DIR}/../src/nrf_edgeai_generated/nrf_edgeai_user_model.c
)
