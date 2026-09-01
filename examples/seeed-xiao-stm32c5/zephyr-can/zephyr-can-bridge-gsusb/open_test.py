#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Firmware A (gs_usb / CANnectivity) — Tier 1 open test.
# Verify the USB vendor-class device, WinUSB/libusb, and python-can control
# path. This test does not transmit CAN frames and does not require a peer.
#
# Install: pip install "python-can[gs_usb]"
# Usage:   python open_test.py                 # channel=0, bitrate=500000
#          python open_test.py 0 250000        # explicit channel and bitrate

import sys
import can

channel = int(sys.argv[1]) if len(sys.argv) > 1 else 0
bitrate = int(sys.argv[2]) if len(sys.argv) > 2 else 500000

print(f"python-can {can.__version__}  ->  open gs_usb channel={channel} bitrate={bitrate}")

try:
    bus = can.Bus(interface="gs_usb", channel=channel, bitrate=bitrate)
except Exception as e:
    print("\nOPEN FAILED:", repr(e))
    low = str(e).lower()
    if any(k in low for k in ("bit", "clock", "timing", "sample", "brp", "tseg", "sjw")):
        print("\n>> Verify that python-can supports the reported FDCAN kernel clock.")
        print("   Some gs_usb timing calculations support only 48 or 80 MHz.")
        print("   See TEST_GUIDE.md and verify the firmware clock configuration.")
    elif any(k in low for k in ("no device", "not found", "could not find", "no matching")):
        print("\n>> No gs_usb device was found. Verify:")
        print("   - the board is running the gs_usb firmware, not SLCAN;")
        print("   - VID:PID 1209:CA01 uses the WinUSB driver;")
        print("   - python-can gs_usb dependencies are installed.")
    else:
        print("\n>> Unexpected error; retain the complete exception for diagnosis.")
    sys.exit(1)

print("\nOPEN OK")
print("  channel_info:", getattr(bus, "channel_info", "n/a"))
print("\nPASS: USB device, WinUSB/libusb, and python-can control path are operational.")
print("Next: connect a second CAN node and run loop.py to verify TX and RX.")

try:
    bus.shutdown()
except Exception:
    pass
