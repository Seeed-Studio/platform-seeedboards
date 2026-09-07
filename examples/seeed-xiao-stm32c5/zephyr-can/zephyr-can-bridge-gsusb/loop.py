#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Firmware A (gs_usb / CANnectivity) — Tier 2 CAN loop test.
# Requires a second CAN node to acknowledge Classic CAN transmission. Run
# open_test.py before this test.
#
# Usage: python loop.py                    # channel=0, bitrate=500000

import sys
import can

channel = int(sys.argv[1]) if len(sys.argv) > 1 else 0
bitrate = int(sys.argv[2]) if len(sys.argv) > 2 else 500000

bus = can.Bus(interface="gs_usb", channel=channel, bitrate=bitrate)
print("opened:", bus.channel_info)

# Transmit one frame. A peer must acknowledge it.
frame = can.Message(arbitration_id=0x123, data=[0xDE, 0xAD, 0xBE, 0xEF],
                    is_extended_id=False)
try:
    bus.send(frame, timeout=2.0)
    print(f"sent  {frame}")
except can.CanError as e:
    print("send FAILED (verify that a second node can acknowledge the frame):", e)

# Receive one frame from the peer.
print("waiting 2s for inbound frames...")
msg = bus.recv(timeout=2.0)
print("recv:", msg)

# CAN FD example; configure the data rate to match the bus:
#   fd = can.Message(arbitration_id=0x456, data=bytes(range(64)),
#                     is_fd=True, bitrate_switch=True)
#   bus.send(fd)

bus.shutdown()
