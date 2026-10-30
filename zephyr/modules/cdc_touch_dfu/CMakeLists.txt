# SPDX-License-Identifier: Apache-2.0

if(CONFIG_CDC_TOUCH_DFU)
	zephyr_library_named(cdc_touch_dfu)
	target_sources(cdc_touch_dfu PRIVATE
		${CMAKE_CURRENT_SOURCE_DIR}/src/cdc_touch_dfu.c
	)
	target_link_libraries(app PUBLIC cdc_touch_dfu)
endif()
