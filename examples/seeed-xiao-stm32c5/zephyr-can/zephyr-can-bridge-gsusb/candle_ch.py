import sys
import can

ch = int(sys.argv[1]) if len(sys.argv) > 1 else 0
print(f"opening candle channel={ch} (fd=True)...", flush=True)
b = can.Bus(interface="candle", channel=ch, fd=True,
            bitrate=500000, data_bitrate=2000000)
print(f"  ch{ch} OK: {b.channel_info}", flush=True)
try:
    b.shutdown()
except Exception:
    pass
