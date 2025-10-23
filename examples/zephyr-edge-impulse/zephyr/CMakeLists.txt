# SPDX-License-Identifier: Apache-2.0
set(BOARD_ROOT "$ENV{ZEPHYR_BASE}/../../platforms/Seeed Studio/zephyr")

cmake_minimum_required(VERSION 3.13.1)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(edge_impulse)

# Needed for colorful output
zephyr_compile_options(-fdiagnostics-color=always)
zephyr_compile_options(-Wno-narrowing)

# Use hardware acceleration for DSP and Neural Network code
# You'll need to disable these on non-Arm cores
add_definitions(-DEIDSP_USE_CMSIS_DSP=1
                -DEIDSP_LOAD_CMSIS_DSP_SOURCES=1
                -DEI_CLASSIFIER_TFLITE_ENABLE_CMSIS_NN=1
                -DEIDSP_QUANTIZE_FILTERBANK=0
                -DARM_MATH_LOOPUNROLL
                -DMBEDTLS_PLATFORM_ZEROIZE_ALT
                )

# Add all required source files
add_subdirectory(../ei-model/edge-impulse-sdk/cmake/zephyr ei_sdk)
add_subdirectory(../firmware-sdk firmware_sdk)
add_subdirectory(../src/inference inference)
add_subdirectory(../src/sensors sensors)
add_subdirectory(../src src)

target_include_directories(app PRIVATE .)
target_include_directories(app PRIVATE ..)
target_include_directories(app PRIVATE ../ei-model)
# Use GLOB to include model files, because model file names differes whether model is EON compiled or not
file(GLOB_RECURSE MODEL_FILES ../ei-model/tflite-model/*.cpp)
target_sources(app PRIVATE ${MODEL_FILES})

target_sources(app PRIVATE ../src/main.cpp)
