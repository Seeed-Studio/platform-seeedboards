#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Use the second board as a peer while SavvyCAN owns the first board.
#   python slcan_peer.py send COM104   # Send frames for 10 seconds
#   python slcan_peer.py recv COM104   # Print received frames for 15 seconds

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
cmd("O")   # Go on-bus

if mode == "send":
    print(f"{port} is on-bus at 500 kbit/s and will send for 10 seconds.")
    frames = [
        "t20081122334455667788",        # Standard 8-byte frame, ID 0x200
        "T001ABCDE8AABBCCDDEEFF0011",   # Extended 8-byte frame
        "t3004DEADBEEF",                # Standard 4-byte frame, ID 0x300
    ]
    end = time.time() + 10
    while time.time() < end:
        for f in frames:
            s.write((f + "\r").encode())
            time.sleep(0.2)
    print("Transmission complete")
else:
    print(f"{port} is on-bus at 500 kbit/s and will receive for 15 seconds.")
    end = time.time() + 15
    while time.time() < end:
        b = s.read(128)
        if b:
            print("  Received:", b)

cmd("C")
s.close()
