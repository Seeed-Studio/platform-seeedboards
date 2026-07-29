#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# 两块板 CAN FD 往返 —— candle 后端，用 serial_number= 分别选两块板（单进程双总线）。
# candle 的 channel= 是"设备内 CAN 通道号"（每块只有 0），选哪块板靠 serial_number。
#
# 序列号来自 diag.py（板子专属，换板要改）。
#   python fd_roundtrip.py

import can

SER_TX = "373234333135510A00550034"
SER_RX = "373234333135510A00760035"

FD64 = bytes((i * 7 + 3) & 0xFF for i in range(64))
FD12 = bytes((i * 7 + 3) & 0xFF for i in range(12))

CASES = [
    ("标准8B",     0x123, b"\x11\x22\x33\x44\x55\x66\x77\x88", {"is_extended_id": False}),
    ("FD12B",      0x557, FD12, {"is_fd": True, "is_extended_id": False}),
    ("FD64B无BRS", 0x555, FD64, {"is_fd": True, "is_extended_id": False}),
    ("FD64B+BRS",  0x556, FD64, {"is_fd": True, "bitrate_switch": True, "is_extended_id": False}),
]

print(f"按序列号开两块板（fd=True, 名义500k/数据2M）：\n  tx={SER_TX}\n  rx={SER_RX}")
try:
    tx = can.Bus(interface="candle", channel=0, serial_number=SER_TX,
                 fd=True, bitrate=500000, data_bitrate=2000000)
    rx = can.Bus(interface="candle", channel=0, serial_number=SER_RX,
                 fd=True, bitrate=500000, data_bitrate=2000000)
except Exception as e:
    print("打开失败:", repr(e))
    raise SystemExit(1)
print("  tx:", tx.channel_info, "\n  rx:", rx.channel_info)

allok = True
for name, aid, data, extra in CASES:
    rx.recv(timeout=0)  # 清残余
    sent = can.Message(arbitration_id=aid, data=data, **extra)
    try:
        tx.send(sent, timeout=2.0)
    except can.CanError as e:
        print(f"  FAIL {name:14}: 发送失败 {e}"); allok = False; continue
    got = rx.recv(timeout=2.0)
    if got is None:
        print(f"  FAIL {name:14}: 接收端 2s 没收到"); allok = False; continue
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
        print(f"        期望 id={aid:#06x} len={len(data)} fd={extra.get('is_fd', False)} "
              f"brs={extra.get('bitrate_switch', False)} data={data[:8].hex()}{'..' if len(data)>8 else ''}")
        print(f"        实际 id={got.arbitration_id:#06x} len={len(gd)} fd={got.is_fd} "
              f"brs={got.bitrate_switch} ext={got.is_extended_id} err={got.is_error_frame} "
              f"data={gd[:8].hex()}{'..' if len(gd)>8 else ''}")

print("\n=== FD 往返全 PASS（含 64 字节 + BRS，字节完整）===" if allok
      else "\n=== 有失败，看上面每行 ===")

for b in (tx, rx):
    try:
        b.shutdown()
    except Exception:
        pass
