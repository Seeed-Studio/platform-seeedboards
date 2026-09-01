#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Find the Seeed CDC port not owned by SavvyCAN and send frames for 12 seconds.
import serial
import serial.tools.list_ports as lp
import time

seeed = [p.device for p in lp.comports() if p.vid == 0x2886]
print(f"Seeed (0x2886) ports: {seeed}")

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
        print(f"  {d} is busy (possibly owned by SavvyCAN): {e}")

if not s:
    print("No available Seeed port. Connect two boards and let SavvyCAN own only one port.")
    raise SystemExit(1)


def cmd(c):
    s.reset_input_buffer()
    s.write((c + "\r").encode())
    time.sleep(0.1)
    return s.read(64)


print(f">>> Sending on {port}; SavvyCAN should show IDs 0x200, 0x1ABCDE, and 0x300.")
cmd("S6")  # 500k
cmd("O")   # Go on-bus

frames = [
    "t20081122334455667788",        # Standard 8-byte frame, ID 0x200
    "T001ABCDE8AABBCCDDEEFF0011",   # Extended 8-byte frame
    "t3004DEADBEEF",                # Standard 4-byte frame, ID 0x300
]
end = time.time() + 12
n = 0
while time.time() < end:
    for f in frames:
        s.write((f + "\r").encode())
        time.sleep(0.2)
        n += 1
print(f"Transmission complete: {n} frames sent.")
cmd("C")
s.close()
