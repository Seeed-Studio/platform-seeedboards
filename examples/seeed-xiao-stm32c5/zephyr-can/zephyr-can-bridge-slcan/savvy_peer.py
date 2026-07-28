#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# 自动找 SavvyCAN 没占用的那个 Seeed CDC 口，上线并循环喷帧 12s，
# 供 SavvyCAN(另一块板) 接收。Bus Traffic 应看到 0x200/0x1abcde/0x300。
import serial
import serial.tools.list_ports as lp
import time

seeed = [p.device for p in lp.comports() if p.vid == 0x2886]
print(f"Seeed(0x2886) 口: {seeed}")

s = None
port = None
for d in seeed:
    try:
        cand = serial.Serial(d, 115200, timeout=0.3)
        cand.dtr = True
        cand.rts = False
        time.sleep(0.4)
        cand.reset_input_buffer()
        s, port = cand, d
        break
    except Exception as e:
        print(f"  {d} 被占用(SavvyCAN 在这？): {e}")

if not s:
    print("没有空闲的 Seeed 口。确认两块板都插着、SavvyCAN 只占一个。")
    raise SystemExit(1)


def cmd(c):
    s.reset_input_buffer()
    s.write((c + "\r").encode())
    time.sleep(0.1)
    return s.read(64)


print(f">>> 用 {port} 喷帧（SavvyCAN 在另一块板接收），盯 Bus Traffic 看 0x200/0x1abcde/0x300 ...")
cmd("S6")  # 500k
cmd("O")   # 上线

frames = [
    "t20081122334455667788",        # 标准 8B, id=0x200
    "T001ABCDE8AABBCCDDEEFF0011",   # 扩展 8B
    "t3004DEADBEEF",                # 标准 4B, id=0x300
]
end = time.time() + 12
n = 0
while time.time() < end:
    for f in frames:
        s.write((f + "\r").encode())
        time.sleep(0.2)
        n += 1
print(f"喷完，共发 {n} 帧。")
cmd("C")
s.close()
