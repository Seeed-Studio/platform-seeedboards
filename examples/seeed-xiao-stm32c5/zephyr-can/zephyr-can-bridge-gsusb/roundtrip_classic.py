#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Two-board Classic CAN round-trip test using the gs_usb backend. Channel 0
# transmits and channel 1 receives; payloads are compared bytewise.
#
#   python roundtrip_classic.py

import can

print("Open two gs_usb channels (Classic CAN 500k): channel 0 TX, channel 1 RX")
try:
    tx = can.Bus(interface="gs_usb", channel=0, bitrate=500000)
    rx = can.Bus(interface="gs_usb", channel=1, bitrate=500000)
except Exception as e:
    print("Open failed:", repr(e))
    print(">> Verify that both boards are connected and run the gs_usb firmware.")
    raise SystemExit(1)

print("  tx:", tx.channel_info, " rx:", rx.channel_info)

cases = [
    # is_extended_id defaults to True; set it explicitly for standard frames.
    ("standard 8B", 0x123,    b"\x11\x22\x33\x44\x55\x66\x77\x88", {"is_extended_id": False}),
    ("standard 4B", 0x456,    b"\xDE\xAD\xBE\xEF", {"is_extended_id": False}),
    ("standard 1B", 0x100,    b"\xA5", {"is_extended_id": False}),
    ("standard 0B", 0x101,    b"", {"is_extended_id": False}),
    ("extended 8B", 0x1ABCDE, b"\xAA\xBB\xCC\xDD\xEE\xFF\x00\x11", {"is_extended_id": True}),
    ("extended 3B", 0x1F004,  b"\x01\x02\x03", {"is_extended_id": True}),
]
allok = True
for name, aid, data, extra in cases:
    rx.recv(timeout=0)  # Discard a pending frame, if any.
    sent = can.Message(arbitration_id=aid, data=data, **extra)
    try:
        tx.send(sent, timeout=2.0)
    except can.CanError as e:
        print(f"  FAIL {name:8}: transmit failed: {e}"); allok = False; continue
    got = rx.recv(timeout=2.0)
    if got is None:
        print(f"  FAIL {name:8}: no frame received within 2 s"); allok = False; continue
    match = (got.arbitration_id == aid
             and bytes(got.data) == data
             and got.is_extended_id == extra.get("is_extended_id", False))
    allok = allok and match
    print(f"  {'PASS' if match else 'FAIL'} {name:8} id={aid:#06x} data={data.hex()}")

print("\n=== PASS: Classic CAN round trip ===" if allok
      else "\n=== FAIL: review the results above ===")
for b in (tx, rx):
    try:
        b.shutdown()
    except Exception:
        pass
