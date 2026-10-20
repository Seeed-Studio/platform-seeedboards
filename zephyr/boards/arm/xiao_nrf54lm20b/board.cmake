# Copyright (c) 2025 Seeed Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

if(CONFIG_SOC_NRF54LM20B_CPUAPP)
  # J-Link does not expose an nRF54LM20B device name yet; Nordic's official
  # nRF54LM20B boards use the LM20A core identifier for the debug probe.
  board_runner_args(jlink "--device=nRF54LM20A_M33" "--speed=4000")
elseif(CONFIG_SOC_NRF54LM20B_CPUFLPR)
  board_runner_args(jlink "--device=nRF54LM20A_RV32" "--speed=4000")
endif()

include(${ZEPHYR_BASE}/boards/common/nrfutil.board.cmake)
include(${ZEPHYR_BASE}/boards/common/jlink.board.cmake)
