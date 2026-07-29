#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# 搭配 SavvyCAN 用：在【另一块板】上当对端（SavvyCAN 连第一块板）。
#   python slcan_peer.py send COM104   # 上线 + 循环发帧 10s（SavvyCAN 应收到）
#   python slcan_peer.py recv COM104   # 上线 + 打印收到的帧 15s（SavvyCAN 发，这里看）
# COM 号用 slcan_check.py 里看到的 Seeed(0x2886) 口。

import sys
import time
import serial

mode = sys.argv[1] if len(sys.argv) > 1 else "send"
port = sys.argv[2] if len(sys.argv) > 2 else "COM104"

s = serial.Serial(port, 115200, timeout=0.3)
s.dtr = True
s.rts = False
time.sleep(0.5)
s.reset_input_buffer()


def cmd(c):
    s.reset_input_buffer()
    s.write((c + "\r").encode())
    time.sleep(0.1)
    return s.read(64)


cmd("S6")  # 500k
cmd("O")   # 上线

if mode == "send":
    print(f"{port} 已上线(500k)，循环发帧 10s —— SavvyCAN(另一块板) 应收到：")
    frames = [
        "t20081122334455667788",        # 标准 8B, id=0x200
        "T001ABCDE8AABBCCDDEEFF0011",   # 扩展 8B
        "t3004DEADBEEF",                # 标准 4B, id=0x300
    ]
    end = time.time() + 10
    while time.time() < end:
        for f in frames:
            s.write((f + "\r").encode())
            time.sleep(0.2)
    print("发送结束")
else:
    print(f"{port} 已上线(500k)，收帧 15s —— SavvyCAN(另一块板) 发，这里打印：")
    end = time.time() + 15
    while time.time() < end:
        b = s.read(128)
        if b:
            print("  收到:", b)

cmd("C")
s.close()
