#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# 最小 candle 探测：单独、干净地试 candle channel=0（不碰 pyusb 枚举、不碰 gs_usb，
# 排除同进程句柄连带占用）。确认 candle 到底能不能访问设备。
#
#   python candle_min.py

import can

print("--- candle channel=0 单独打开 ---")
try:
    b = can.Bus(interface="candle", channel=0, fd=True,
                bitrate=500000, data_bitrate=2000000)
    print("OK:", b.channel_info)
    try:
        b.shutdown()
    except Exception:
        pass
except Exception as e:
    print("FAIL:", repr(e))

print("\n--- 对比：gs_usb channel=0 单独打开（同一个进程，但 candle 失败不影响它）---")
try:
    b = can.Bus(interface="gs_usb", channel=0, bitrate=500000)
    print("OK:", b.channel_info)
    try:
        b.shutdown()
    except Exception:
        pass
except Exception as e:
    print("FAIL:", repr(e))
