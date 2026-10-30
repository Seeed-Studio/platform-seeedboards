# Copyright (c) 2026 Seeed Technology Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

# Board USB bring-up (device + descriptors + CDC ACM class; VID/PID from
# Kconfig). The cdc_touch_dfu module rides on the contexts created here.
zephyr_library()
zephyr_library_sources(board.c)
