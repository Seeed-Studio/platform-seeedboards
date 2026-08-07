# SPDX-License-Identifier: Apache-2.0

if(CONFIG_XIAO_DFU_RESET)
	zephyr_library_named(xiao_dfu_reset)
	target_sources(xiao_dfu_reset PRIVATE
		${CMAKE_CURRENT_SOURCE_DIR}/src/xiao_dfu_reset.c
	)
	target_link_libraries(app PUBLIC xiao_dfu_reset)
endif()
