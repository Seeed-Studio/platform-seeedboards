#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Two-board Classic CAN and CAN FD round-trip test using python-can-candle.
# Channel 0 transmits and channel 1 receives; payloads are compared bytewise.
#
# Both boards must run the gs_usb firmware and share CANH, CANL, and GND. Use
# correct termination and power both boards. Install python-can and python-can-candle.
#
#   python roundtrip.py

import can

# Deterministic patterns detect truncation, reordering, or offset errors.
FD64 = bytes((i * 7 + 3) & 0xFF for i in range(64))
FD12 = bytes((i * 7 + 3) & 0xFF for i in range(12))

print("Open two candle channels (FD, nominal 500k, data 2M): channel 0 TX, channel 1 RX")
try:
    tx = can.Bus(interface="candle", channel=0, fd=True, bitrate=500000, data_bitrate=2000000)
    rx = can.Bus(interface="candle", channel=1, fd=True, bitrate=500000, data_bitrate=2000000)
except Exception as e:
    print("Open failed:", repr(e))
    print(">> Verify dependencies, firmware, and both USB connections.")
    raise SystemExit(1)

print("  tx:", tx.channel_info, " rx:", rx.channel_info)
print("  The two channel descriptions must identify different devices.\n")

cases = [
    ("standard 8B",  0x123,     b"\x11\x22\x33\x44\x55\x66\x77\x88", {}),
    ("standard 4B",  0x456,     b"\xDE\xAD\xBE\xEF", {}),
    ("standard 0B",  0x101,     b"", {}),
    ("extended 8B",  0x1ABCDE,  b"\xAA\xBB\xCC\xDD\xEE\xFF\x00\x11", {"is_extended_id": True}),
    ("FD 12B",       0x557,     FD12, {"is_fd": True}),
    ("FD 64B no BRS", 0x555,    FD64, {"is_fd": True}),
    ("FD 64B +BRS",  0x556,     FD64, {"is_fd": True, "bitrate_switch": True}),
]

allok = True
for name, aid, data, extra in cases:
    rx.recv(timeout=0)  # Discard a pending frame, if any.
    sent = can.Message(arbitration_id=aid, data=data, **extra)
    try:
        tx.send(sent, timeout=2.0)
    except can.CanError as e:
        print(f"  FAIL {name:14}: transmit failed: {e}")
        allok = False
        continue
    got = rx.recv(timeout=2.0)
    if got is None:
        print(f"  FAIL {name:14}: no frame received within 2 s")
        allok = False
        continue
    match = (got.arbitration_id == aid
             and bytes(got.data) == data
             and got.is_extended_id == extra.get("is_extended_id", False)
             and got.is_fd == extra.get("is_fd", False)
             and got.bitrate_switch == extra.get("bitrate_switch", False))
    allok = allok and match
    head = data[:8].hex()
    tail = ".." if len(data) > 8 else ""
    print(f"  {'PASS' if match else 'FAIL'} {name:14} id={aid:#06x} "
          f"data={head}{tail}({len(data)}B) fd={extra.get('is_fd', False)} "
          f"brs={extra.get('bitrate_switch', False)}")

print("\n=== PASS: Classic CAN and CAN FD round trip ===" if allok
      else "\n=== FAIL: review the results above ===")

for b in (tx, rx):
    try:
        b.shutdown()
    except Exception:
        pass   # Ignore backend shutdown errors after test completion.
