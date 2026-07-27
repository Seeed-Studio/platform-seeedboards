#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Firmware A (gs_usb / CANnectivity) — Tier 2 CAN loop test.
# ⚠ 需要第二个 CAN 节点（经典 CAN 发送要 ACK）。先跑 open_test.py 通过再用。
#
# 运行：  python loop.py                   # channel=0, bitrate=500000

import sys
import can

channel = int(sys.argv[1]) if len(sys.argv) > 1 else 0
bitrate = int(sys.argv[2]) if len(sys.argv) > 2 else 500000

bus = can.Bus(interface="gs_usb", channel=channel, bitrate=bitrate)
print("opened:", bus.channel_info)

# 发一帧（需要总线上有对端回 ACK，否则 bus-off）
frame = can.Message(arbitration_id=0x123, data=[0xDE, 0xAD, 0xBE, 0xEF],
                    is_extended_id=False)
try:
    bus.send(frame, timeout=2.0)
    print(f"sent  {frame}")
except can.CanError as e:
    print("send FAILED（单节点无 ACK → bus-off? 加第二个 CAN 节点）:", e)

# 收（对端在发才能收到）
print("waiting 2s for inbound frames...")
msg = bus.recv(timeout=2.0)
print("recv:", msg)

# CAN FD（A 支持；数据相速率按你总线配置）：
#   fd = can.Message(arbitration_id=0x456, data=bytes(range(64)),
#                     is_fd=True, bitrate_switch=True)
#   bus.send(fd)

bus.shutdown()
