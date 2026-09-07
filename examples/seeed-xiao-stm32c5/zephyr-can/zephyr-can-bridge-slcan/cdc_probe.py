import sys, time, serial, serial.tools.list_ports as lp

seeed = [p for p in lp.comports() if p.vid == 0x2886]
if not seeed:
    print("No Seeed CDC port found"); sys.exit(1)
port = seeed[0].device
print(f"Probing {port} (DTR=True, 115200)")
s = serial.Serial(port, 115200, timeout=0.3)
s.dtr = True; s.rts = False; time.sleep(0.6); s.reset_input_buffer()

def send_and_dump(label, data, wait=2.0):
    print(f"\n--- Sending {label} ---")
    s.write(data);
    try: s.flush()
    except Exception: pass
    t = time.time(); total = b""
    while time.time() - t < wait:
        b = s.read(64)
        if b:
            total += b
            print(f"  +{time.time()-t:.2f}s received {len(b)} bytes: {b!r}")
    if not total:
        print(f"  (no response within {wait}s)")
    return total

send_and_dump("V\\r", b"V\r")
send_and_dump("invalid ZZZ\\r (expect BEL=0x07)", b"ZZZ\r")
send_and_dump("S6\\r", b"S6\r")
s.close()
print("\nIf all responses are empty, the CDC path is not working. V1013/BEL confirms the CDC path works.")
