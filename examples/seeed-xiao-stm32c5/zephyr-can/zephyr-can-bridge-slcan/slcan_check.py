#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Validate the Lawicel text protocol used by SavvyCAN with two bridge boards.
#
#   python slcan_check.py [TX_COM] [RX_COM]

import sys
import time
import serial
import serial.tools.list_ports as lp

print("=== Serial port enumeration ===")
allp = list(lp.comports())
for p in allp:
    print(f"  {p.device} vid={p.vid if p.vid is None else hex(p.vid)} "
          f"pid={p.pid if p.pid is None else hex(p.pid)} sn={p.serial_number} {p.description}")

if len(sys.argv) >= 3:
    TX_P, RX_P = sys.argv[1], sys.argv[2]
else:
    seeed = [p for p in allp if p.vid == 0x2886]
    print(f"\nSeeed (0x2886) CDC ports: {len(seeed)}")
    if len(seeed) < 2:
        print("Two boards are required. Specify ports manually with: python slcan_check.py COM3 COM4")
        sys.exit(1)
    TX_P, RX_P = seeed[0].device, seeed[1].device
print(f"  -> tx={TX_P}  rx={RX_P}\n")


def open_p(p):
    s = serial.Serial(p, 115200, timeout=0.5)
    s.dtr = True   # CDC ACM normally requires DTR before receiving data
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

print("=== Open both boards with S6 (500 kbit/s) and O ===")
for nm, s in ((TX_P, tx), (RX_P, rx)):
    print(f"  {nm}: S6->{cmd(s, 'S6')!r}  O->{cmd(s, 'O')!r}")

print("\n=== SavvyCAN handshake commands V/N/F on TX ===")
for c, exp in (("V", b"V1013"), ("N", b"N0001"), ("F", b"F00")):
    r = cmd(tx, c)
    print(f"  {'PASS' if r.startswith(exp) else 'FAIL'} {c}->{r!r} (expected prefix {exp!r})")

print("\n=== Board-to-board transfer (TX acknowledgement: \\r=OK, \\x07=error) ===")
cases = [
    ("standard 8-byte", "t12381122334455667788"),
    ("extended 8-byte", "T001ABCDE8AABBCCDDEEFF0011"),
    ("standard 4-byte", "t4564DEADBEEF"),
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
    print(f"        sent {frame}")
    print(f"        TX response {ack!r}   RX data {got!r}")

cmd(tx, "C")
cmd(rx, "C")
tx.close()
rx.close()
print("\n=== " + ("SavvyCAN/SLCAN validation: ALL PASS ===" if allok else "Validation failed; review the output above ==="))
