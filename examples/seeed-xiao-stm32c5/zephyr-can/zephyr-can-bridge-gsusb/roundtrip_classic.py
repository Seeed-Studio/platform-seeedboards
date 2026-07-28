#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# 两块板（都刷固件 A）之间 CLASSIC CAN 往返自测 —— 用 gs_usb 后端
# （已验证能访问设备；candle 在 Windows 上 access denied，FD 暂走不了）。
# channel=0 发，channel=1 收，逐字节比对。
#
#   python roundtrip_classic.py

import can

print("用 gs_usb 打开两块板（classic 500k）：channel=0(发) + channel=1(收)")
try:
    tx = can.Bus(interface="gs_usb", channel=0, bitrate=500000)
    rx = can.Bus(interface="gs_usb", channel=1, bitrate=500000)
except Exception as e:
    print("打开失败:", repr(e))
    print(">> 若 channel=0 OK、channel=1 FAIL：两块板都插了吗？都是固件 A？")
    raise SystemExit(1)

print("  tx:", tx.channel_info, " rx:", rx.channel_info)

cases = [
    # 注意：python-can 的 can.Message 默认 is_extended_id=True！标准帧必须显式写 False。
    ("标准 8B", 0x123,    b"\x11\x22\x33\x44\x55\x66\x77\x88", {"is_extended_id": False}),
    ("标准 4B", 0x456,    b"\xDE\xAD\xBE\xEF", {"is_extended_id": False}),
    ("标准 1B", 0x100,    b"\xA5", {"is_extended_id": False}),
    ("标准 0B", 0x101,    b"", {"is_extended_id": False}),
    ("扩展 8B", 0x1ABCDE, b"\xAA\xBB\xCC\xDD\xEE\xFF\x00\x11", {"is_extended_id": True}),
    ("扩展 3B", 0x1F004,  b"\x01\x02\x03", {"is_extended_id": True}),
]
allok = True
for name, aid, data, extra in cases:
    rx.recv(timeout=0)  # 清残余
    sent = can.Message(arbitration_id=aid, data=data, **extra)
    try:
        tx.send(sent, timeout=2.0)
    except can.CanError as e:
        print(f"  FAIL {name:8}: 发送失败 {e}"); allok = False; continue
    got = rx.recv(timeout=2.0)
    if got is None:
        print(f"  FAIL {name:8}: 接收端 2s 没收到"); allok = False; continue
    match = (got.arbitration_id == aid
             and bytes(got.data) == data
             and got.is_extended_id == extra.get("is_extended_id", False))
    allok = allok and match
    print(f"  {'PASS' if match else 'FAIL'} {name:8} id={aid:#06x} data={data.hex()}")

print("\n=== 全部 PASS（classic 端到端、字节完整）===" if allok
      else "\n=== 有失败，看上面每行 ===")
for b in (tx, rx):
    try:
        b.shutdown()
    except Exception:
        pass
