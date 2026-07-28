#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# 诊断：candle/gs_usb 在 Windows 上打开两块板为什么失败。
# 列出 pyusb 看到几个 1209:CA01 设备、它们的序列号/接口类、以及 candle 逐个 channel 能不能开。

import logging
# 把 python-can / pyusb 内部日志全打开
logging.basicConfig(level=logging.DEBUG)
for n in ("can", "can.interfaces.gs_usb", "gs_usb", "usb", "usb.backend"):
    logging.getLogger(n).setLevel(logging.DEBUG)

print("=" * 60)
print("1) pyusb 枚举 VID 1209 : PID CA01")
print("=" * 60)
import usb.core
import usb.util

devs = list(usb.core.find(find_all=True, idVendor=0x1209, idProduct=0xCA01))
print(f"\n找到 {len(devs)} 个 1209:CA01 设备：")
for i, d in enumerate(devs):
    try:
        sn = usb.util.get_string(d, d.iSerialNumber) if d.iSerialNumber else "(无 iSerialNumber)"
    except Exception as e:
        sn = f"(读序列号失败: {e})"
    try:
        prod = usb.util.get_string(d, d.iProduct) if d.iProduct else "(无 iProduct)"
    except Exception:
        prod = "?"
    print(f"  [{i}] bus={d.bus} address={d.address} serial={sn!r} product={prod!r}")
    for cfg in d:
        for itf in cfg:
            print(f"        cfg{cfg.bConfigurationValue} "
                  f"itf{itf.bInterfaceNumber} class=0x{itf.bInterfaceClass:02x} "
                  f"(vendor=0xff 才对)")

print("\n" + "=" * 60)
print("2) 逐个试 candle channel 0 / 1（每次开完就关，避免互相占用）")
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
            print(f"    (shutdown 忽略: {e})")
    except Exception as e:
        print(f"  channel={ch}: FAIL  {e!r}")

print("\n" + "=" * 60)
print("3) 也试一下 gs_usb（确认不是 candle 单独的问题）")
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
