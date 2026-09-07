#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Two-board CAN FD round trip using the candle backend. Select each board by
# serial_number because channel identifies the CAN channel within a device.
#
# Obtain board-specific serial numbers with diag.py and update them below.
#   python fd_roundtrip.py

import can

SER_TX = "373234333135510A00550034"
SER_RX = "373234333135510A00760035"

FD64 = bytes((i * 7 + 3) & 0xFF for i in range(64))
FD12 = bytes((i * 7 + 3) & 0xFF for i in range(12))

CASES = [
    ("standard 8B", 0x123, b"\x11\x22\x33\x44\x55\x66\x77\x88", {"is_extended_id": False}),
    ("FD12B",      0x557, FD12, {"is_fd": True, "is_extended_id": False}),
    ("FD64B no BRS", 0x555, FD64, {"is_fd": True, "is_extended_id": False}),
    ("FD64B+BRS",  0x556, FD64, {"is_fd": True, "bitrate_switch": True, "is_extended_id": False}),
]

print(f"Open two boards by serial number (FD, nominal 500k, data 2M):\n  tx={SER_TX}\n  rx={SER_RX}")
try:
    tx = can.Bus(interface="candle", channel=0, serial_number=SER_TX,
                 fd=True, bitrate=500000, data_bitrate=2000000)
    rx = can.Bus(interface="candle", channel=0, serial_number=SER_RX,
                 fd=True, bitrate=500000, data_bitrate=2000000)
except Exception as e:
    print("Open failed:", repr(e))
    raise SystemExit(1)
print("  tx:", tx.channel_info, "\n  rx:", rx.channel_info)

allok = True
for name, aid, data, extra in CASES:
    rx.recv(timeout=0)  # Discard a pending frame, if any.
    sent = can.Message(arbitration_id=aid, data=data, **extra)
    try:
        tx.send(sent, timeout=2.0)
    except can.CanError as e:
        print(f"  FAIL {name:14}: transmit failed: {e}"); allok = False; continue
    got = rx.recv(timeout=2.0)
    if got is None:
        print(f"  FAIL {name:14}: no frame received within 2 s"); allok = False; continue
    match = (got.arbitration_id == aid
             and bytes(got.data) == data
             and got.is_extended_id == extra.get("is_extended_id", False)
             and got.is_fd == extra.get("is_fd", False)
             and got.bitrate_switch == extra.get("bitrate_switch", False))
    allok = allok and match
    if match:
        print(f"  PASS {name:14} id={aid:#06x} ({len(data)}B) "
              f"fd={extra.get('is_fd', False)} brs={extra.get('bitrate_switch', False)}")
    else:
        gd = bytes(got.data)
        print(f"  FAIL {name:14}:")
        print(f"        expected id={aid:#06x} len={len(data)} fd={extra.get('is_fd', False)} "
              f"brs={extra.get('bitrate_switch', False)} data={data[:8].hex()}{'..' if len(data)>8 else ''}")
        print(f"        actual id={got.arbitration_id:#06x} len={len(gd)} fd={got.is_fd} "
              f"brs={got.bitrate_switch} ext={got.is_extended_id} err={got.is_error_frame} "
              f"data={gd[:8].hex()}{'..' if len(gd)>8 else ''}")

print("\n=== PASS: CAN FD round trip, including 64-byte BRS frames ===" if allok
      else "\n=== FAIL: review the results above ===")

for b in (tx, rx):
    try:
        b.shutdown()
    except Exception:
        pass
