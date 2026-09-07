#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Minimal candle probe. Open channel 0 without pyusb enumeration or gs_usb so
# another backend handle in the same process cannot affect the result.
#
#   python candle_min.py

import can

print("--- Open candle channel 0 independently ---")
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

print("\n--- Comparison: open gs_usb channel 0 independently ---")
try:
    b = can.Bus(interface="gs_usb", channel=0, bitrate=500000)
    print("OK:", b.channel_info)
    try:
        b.shutdown()
    except Exception:
        pass
except Exception as e:
    print("FAIL:", repr(e))
