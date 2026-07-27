# SPDX-License-Identifier: Apache-2.0

# Auto-add the module source to the app target when enabled.
if(CONFIG_UF2_DFU_RESET)
	zephyr_library_named(uf2_dfu_reset)
	target_sources(uf2_dfu_reset PRIVATE
		${CMAKE_CURRENT_SOURCE_DIR}/src/uf2_dfu_reset.c
	)
	target_include_directories(uf2_dfu_reset PUBLIC
		${CMAKE_CURRENT_SOURCE_DIR}/include
	)
	target_link_libraries(app PUBLIC uf2_dfu_reset)
endif()
