#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Diagnose candle/gs_usb access to two boards on Windows. Enumerate 1209:CA01
# devices and test each channel with both backends.

import logging
# Enable detailed python-can and pyusb logging.
logging.basicConfig(level=logging.DEBUG)
for n in ("can", "can.interfaces.gs_usb", "gs_usb", "usb", "usb.backend"):
    logging.getLogger(n).setLevel(logging.DEBUG)

print("=" * 60)
print("1) Enumerate VID 1209 : PID CA01 with pyusb")
print("=" * 60)
import usb.core
import usb.util

devs = list(usb.core.find(find_all=True, idVendor=0x1209, idProduct=0xCA01))
print(f"\nFound {len(devs)} device(s) with VID:PID 1209:CA01:")
for i, d in enumerate(devs):
    try:
        sn = usb.util.get_string(d, d.iSerialNumber) if d.iSerialNumber else "(no iSerialNumber)"
    except Exception as e:
        sn = f"(failed to read serial number: {e})"
    try:
        prod = usb.util.get_string(d, d.iProduct) if d.iProduct else "(no iProduct)"
    except Exception:
        prod = "?"
    print(f"  [{i}] bus={d.bus} address={d.address} serial={sn!r} product={prod!r}")
    for cfg in d:
        for itf in cfg:
            print(f"        cfg{cfg.bConfigurationValue} "
                  f"itf{itf.bInterfaceNumber} class=0x{itf.bInterfaceClass:02x} "
                  f"(expected vendor class: 0xff)")

print("\n" + "=" * 60)
print("2) Test candle channels 0 and 1 independently")
print("=" * 60)
import can

for ch in (0, 1):
    try:
        b = can.Bus(interface="candle", channel=ch, fd=True,
                    bitrate=500000, data_bitrate=2000000)
        print(f"  channel={ch}: OK   info={b.channel_info}")
        try:
            b.shutdown()
        except Exception as e:
            print(f"    (shutdown error ignored: {e})")
    except Exception as e:
        print(f"  channel={ch}: FAIL  {e!r}")

print("\n" + "=" * 60)
print("3) Test gs_usb for comparison")
print("=" * 60)
for ch in (0, 1):
    try:
        b = can.Bus(interface="gs_usb", channel=ch, bitrate=500000)
        print(f"  gs_usb channel={ch}: OK   info={b.channel_info}")
        try:
            b.shutdown()
        except Exception:
            pass
    except Exception as e:
        print(f"  gs_usb channel={ch}: FAIL  {e!r}")
