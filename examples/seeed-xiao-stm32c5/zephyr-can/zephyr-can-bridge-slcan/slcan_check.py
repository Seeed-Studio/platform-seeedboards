#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# SavvyCAN / SLCAN 协议验证（固件 B）—— pyserial 直接说 Lawicel 文本协议，
# 这正是 SavvyCAN 的 Lawicel 连接所走的协议。两块 B 板：tx(COM) 发、rx(COM) 收。
#
#   python slcan_check.py [TX_COM] [RX_COM]   # 不带参数则自动找 Seeed(0x2886) 串口

import sys
import time
import serial
import serial.tools.list_ports as lp

print("=== 串口枚举 ===")
allp = list(lp.comports())
for p in allp:
    print(f"  {p.device} vid={p.vid if p.vid is None else hex(p.vid)} "
          f"pid={p.pid if p.pid is None else hex(p.pid)} sn={p.serial_number} {p.description}")

if len(sys.argv) >= 3:
    TX_P, RX_P = sys.argv[1], sys.argv[2]
else:
    seeed = [p for p in allp if p.vid == 0x2886]
    print(f"\nSeeed(0x2886) CDC: {len(seeed)} 个")
    if len(seeed) < 2:
        print("不足两块！确认两块都刷固件 B、插着 USB。或手动指定：python slcan_check.py COM3 COM4")
        sys.exit(1)
    TX_P, RX_P = seeed[0].device, seeed[1].device
print(f"  -> tx={TX_P}  rx={RX_P}\n")


def open_p(p):
    s = serial.Serial(p, 115200, timeout=0.5)
    s.dtr = True   # CDC ACM 通常需要 DTR 置位，固件 uart_irq_rx_ready 才会就绪
    s.rts = False
    time.sleep(0.5)
    s.reset_input_buffer()
    return s


def cmd(s, c):
    s.reset_input_buffer()
    s.write((c + "\r").encode())
    time.sleep(0.12)
    return s.read(64)


tx = open_p(TX_P)
rx = open_p(RX_P)

print("=== 握手 S6(500k)/O(上线) 两块 ===")
for nm, s in ((TX_P, tx), (RX_P, rx)):
    print(f"  {nm}: S6->{cmd(s, 'S6')!r}  O->{cmd(s, 'O')!r}")

print("\n=== SavvyCAN 握手命令 V/N/F (tx) ===")
for c, exp in (("V", b"V1013"), ("N", b"N0001"), ("F", b"F00")):
    r = cmd(tx, c)
    print(f"  {'PASS' if r.startswith(exp) else 'FAIL'} {c}->{r!r} (期望开头 {exp!r})")

print("\n=== 板间往返（tx 发、rx 收；同时看 tx 的应答 \\r=OK / \\x07=错）===")
cases = [
    ("标准8B", "t12381122334455667788"),
    ("扩展8B", "T001ABCDE8AABBCCDDEEFF0011"),
    ("标准4B", "t4564DEADBEEF"),
]
allok = True
for name, frame in cases:
    tx.reset_input_buffer()
    rx.reset_input_buffer()
    tx.write((frame + "\r").encode())
    time.sleep(0.15)
    ack = tx.read(64)
    got = rx.read(128)
    want = frame.encode()
    ok = got.strip() == want
    allok = allok and ok
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"        发 {frame}")
    print(f"        tx应答 {ack!r}   rx收到 {got!r}")

cmd(tx, "C")
cmd(rx, "C")
tx.close()
rx.close()
print("\n=== " + ("SavvyCAN/SLCAN 协议验证 全 PASS ===" if allok else "有失败（看上面，可能是 toupper bug）==="))
