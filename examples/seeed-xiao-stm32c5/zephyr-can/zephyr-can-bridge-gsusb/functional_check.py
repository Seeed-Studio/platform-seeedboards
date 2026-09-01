#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# gs_usb/CANnectivity firmware functional verification with python-can
# ===========================================================================
# This script verifies the bridge and demonstrates the corresponding
# python-can interfaces.
#
# Usage:
#   python functional_check.py caps
#   python functional_check.py monitor 5
#   python functional_check.py tx
#   python functional_check.py throughput 500
#   python functional_check.py filter 0x200 0x700 5
#   python functional_check.py all 3
#
# The board must run the gs_usb firmware and the bus must contain a peer that
# acknowledges transmitted frames. Install: pip install python-can python-can-candle

import sys
import time
import can

# All python-can interaction starts with can.Bus. The backend communicates with
# the device through libusb/WinUSB control and bulk transfers.


# "candle" supports CAN FD. The built-in "gs_usb" backend is Classic CAN only.
INTERFACE = "candle"


def open_bus(bitrate=500000, data_bitrate=2000000, filters=None):
    """Open the CAN bus.

    bitrate is the nominal/arbitration rate. data_bitrate is the CAN FD data
    rate used by BRS frames and is supported by the candle backend.
    """
    if INTERFACE == "candle":
        bus = can.Bus(interface="candle", channel=0, fd=True,
                      bitrate=bitrate, data_bitrate=data_bitrate)
    else:
        bus = can.Bus(interface="gs_usb", channel=0, bitrate=bitrate)
    if filters:
        bus.set_filters(filters)  # Apply hardware/driver-level filters.
    return bus


# ---------------------------------------------------------------------------
# 1) Capability query
# ---------------------------------------------------------------------------
def cmd_caps():
    """Open the device and print its reported capabilities."""
    bus = open_bus()
    print("=== gs_usb device ===")
    print("  channel_info :", bus.channel_info)
    # protocol == CAN_FD (1) indicates CAN FD support.
    print("  protocol     :", getattr(bus, "protocol", "n/a"),
          "(CAN_FD=1 indicates FD support)")
    print("  state        :", getattr(bus, "state", "n/a"))
    print("\nConfirm CAN FD operation with the `tx` test.")
    bus.shutdown()


# ---------------------------------------------------------------------------
# 2) Receive monitor using Notifier and Listener
# ---------------------------------------------------------------------------
def cmd_monitor(duration=5):
    """Dispatch received messages to a console printer and Vector ASC logger.
    """
    bus = open_bus()
    print(f"=== Monitor for {duration}s and write capture.asc ===")
    notifier = can.Notifier(bus, [can.Printer(), can.Logger("capture.asc")])
    time.sleep(duration)
    notifier.stop()
    bus.shutdown()
    print("--> capture.asc written; it can be imported into SavvyCAN.")


# ---------------------------------------------------------------------------
# 3) Representative transmit cases
# ---------------------------------------------------------------------------
def cmd_tx():
    """Transmit representative Classic CAN, RTR, and CAN FD frames."""
    bus = open_bus()

    def tx(label, msg):
        try:
            bus.send(msg, timeout=1.0)
            print(f"  OK   {label:22} {msg}")
        except can.CanError as e:
            print(f"  FAIL {label:22} {e}")

    print("=== Transmit test set ===")
    # is_extended_id defaults to True; set it explicitly for standard frames.
    tx("standard 11-bit 8B", can.Message(arbitration_id=0x123, is_extended_id=False,
                                         data=b"\x11\x22\x33\x44\x55\x66\x77\x88"))
    tx("standard 0B",        can.Message(arbitration_id=0x100, is_extended_id=False))
    tx("extended 29-bit 8B", can.Message(arbitration_id=0x1ABCDE, is_extended_id=True,
                                         data=b"\xAA\xBB\xCC\xDD\xEE\xFF\x00\x11"))
    tx("standard RTR",       can.Message(arbitration_id=0x200, is_extended_id=False,
                                         is_remote_frame=True))
    tx("FD 64B without BRS", can.Message(arbitration_id=0x555, data=bytes(64),
                                         is_fd=True, bitrate_switch=False))
    tx("FD 64B +BRS",        can.Message(arbitration_id=0x556, data=bytes(64),
                                         is_fd=True, bitrate_switch=True))
    tx("FD 12B(DLC=12)",     can.Message(arbitration_id=0x557, data=bytes(12), is_fd=True))
    bus.shutdown()
    print("If FD+BRS fails, verify data_bitrate and backend CAN FD support.")


# ---------------------------------------------------------------------------
# 4) Throughput and loss
# ---------------------------------------------------------------------------
def cmd_throughput(n=500):
    """Transmit n frames and report the achieved rate and success count."""
    bus = open_bus()
    print(f"=== Burst transmit: {n} frames ===")
    t0 = time.time()
    ok = 0
    for i in range(n):
        try:
            bus.send(can.Message(arbitration_id=0x300 + (i & 0x0F), data=bytes([i & 0xFF] * 4)),
                     timeout=0.5)
            ok += 1
        except can.CanError:
            pass
    dt = max(time.time() - t0, 1e-6)
    print(f"  Success {ok}/{n}, elapsed {dt:.2f}s, rate {ok / dt:.0f} frames/s")
    bus.shutdown()


# ---------------------------------------------------------------------------
# 5) Receive filtering
# ---------------------------------------------------------------------------
def cmd_filter(can_id, mask, duration=5):
    """Accept frames for which (id & mask) == (can_id & mask)."""
    bus = open_bus(filters=[{"can_id": can_id, "can_mask": mask, "extended": False}])
    print(f"=== Filter id&{mask:#x}=={can_id & mask:#x}; monitor {duration}s ===")
    end = time.time() + duration
    seen = 0
    while time.time() < end:
        msg = bus.recv(timeout=0.5)
        if msg:
            print("  ", msg)
            seen += 1
    print(f"  Received {seen} matching frames.")
    bus.shutdown()


# ---------------------------------------------------------------------------
def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "caps"
    if cmd == "caps":
        cmd_caps()
    elif cmd == "monitor":
        cmd_monitor(int(sys.argv[2]) if len(sys.argv) > 2 else 5)
    elif cmd == "tx":
        cmd_tx()
    elif cmd == "throughput":
        cmd_throughput(int(sys.argv[2]) if len(sys.argv) > 2 else 500)
    elif cmd == "filter":
        cmd_filter(int(sys.argv[2], 0), int(sys.argv[3], 0),
                   int(sys.argv[4]) if len(sys.argv) > 4 else 5)
    elif cmd == "all":
        d = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        cmd_caps(); cmd_monitor(d); cmd_tx(); cmd_throughput(500)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
