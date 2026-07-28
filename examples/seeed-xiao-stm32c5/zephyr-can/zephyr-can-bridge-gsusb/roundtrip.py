#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# 两块板（都刷固件 A）之间的 CAN 往返自测 —— 经典 + CAN FD 全覆盖。
# channel=0 的板子发，channel=1 的板子收，逐字节比对（含 64 字节 FD 帧）。
# 用 candle 后端（python-can-candle）——自带的 gs_usb 包经典-only，FD 会崩。
#
# 前提：两块 XIAO 都刷固件 A；两板 CAN_H↔CAN_L 交叉、共地、120Ω终端；都 USB 供电。
# 安装：pip install python-can python-can-candle
#
#   python roundtrip.py

import can

# 64/12 字节的变化图案，便于查字节完整性（截断/交换/错位都能发现）
FD64 = bytes((i * 7 + 3) & 0xFF for i in range(64))
FD12 = bytes((i * 7 + 3) & 0xFF for i in range(12))

print("用 candle 打开两块板（fd=True, 名义500k/数据2M）：channel=0(发) + channel=1(收)")
try:
    tx = can.Bus(interface="candle", channel=0, fd=True, bitrate=500000, data_bitrate=2000000)
    rx = can.Bus(interface="candle", channel=1, fd=True, bitrate=500000, data_bitrate=2000000)
except Exception as e:
    print("打开失败:", repr(e))
    print(">> 检查：pip install python-can-candle；两块板都刷了固件 A；都插着 USB。")
    raise SystemExit(1)

print("  tx:", tx.channel_info, " rx:", rx.channel_info)
print("  （若两个 info 完全一样 = channel 没分到两块板，贴回去我改寻址）\n")

cases = [
    ("标准 8B",      0x123,     b"\x11\x22\x33\x44\x55\x66\x77\x88", {}),
    ("标准 4B",      0x456,     b"\xDE\xAD\xBE\xEF", {}),
    ("标准 0B",      0x101,     b"", {}),
    ("扩展 8B",      0x1ABCDE,  b"\xAA\xBB\xCC\xDD\xEE\xFF\x00\x11", {"is_extended_id": True}),
    # CAN FD（固件 A 卖点；两块板都 fd=True 才能往返）：
    ("FD 12B",       0x557,     FD12, {"is_fd": True}),
    ("FD 64B 无BRS", 0x555,     FD64, {"is_fd": True}),
    ("FD 64B +BRS",  0x556,     FD64, {"is_fd": True, "bitrate_switch": True}),
]

allok = True
for name, aid, data, extra in cases:
    rx.recv(timeout=0)  # 清接收端残余
    sent = can.Message(arbitration_id=aid, data=data, **extra)
    try:
        tx.send(sent, timeout=2.0)
    except can.CanError as e:
        print(f"  FAIL {name:14}: 发送失败 {e}")
        allok = False
        continue
    got = rx.recv(timeout=2.0)
    if got is None:
        print(f"  FAIL {name:14}: 接收端 2s 没收到（CAN 线/终端电阻/channel寻址？）")
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

print("\n=== 全部 PASS（classic+FD 端到端、字节完整）===" if allok
      else "\n=== 有失败，看上面每行 ===")

for b in (tx, rx):
    try:
        b.shutdown()
    except Exception:
        pass   # libusb Windows shutdown 偶发 access violation，忽略
