import sys, time, serial, serial.tools.list_ports as lp

seeed = [p for p in lp.comports() if p.vid == 0x2886]
if not seeed:
    print("没找到 Seeed CDC"); sys.exit(1)
port = seeed[0].device
print(f"探活 {port} (DTR=True, 115200)")
s = serial.Serial(port, 115200, timeout=0.3)
s.dtr = True; s.rts = False; time.sleep(0.6); s.reset_input_buffer()

def send_and_dump(label, data, wait=2.0):
    print(f"\n--- 发 {label} ---")
    s.write(data);
    try: s.flush()
    except Exception: pass
    t = time.time(); total = b""
    while time.time() - t < wait:
        b = s.read(64)
        if b:
            total += b
            print(f"  +{time.time()-t:.2f}s 收到 {len(b)} 字节: {b!r}")
    if not total:
        print(f"  ({wait}s 内没有任何响应)")
    return total

send_and_dump("V\\r", b"V\r")
send_and_dump("垃圾 ZZZ\\r (应回 BEL=0x07)", b"ZZZ\r")
send_and_dump("S6\\r", b"S6\r")
s.close()
print("\n结论：若上面全空 = B 的 CDC 管道没通（固件侧问题）；若有 V1013/BEL = 管道通，问题在别处。")
