#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# Firmware A (gs_usb / CANnectivity) — Tier 1 open test.
# 验 USB vendor-class 设备端 + WinUSB/libusb + python-can 控制通道，
# 不发 CAN 帧、不需要 CAN 对端。
#
# 安装：  pip install "python-can[gs_usb]"
# 运行：  python open_test.py                 # channel=0, bitrate=500000
#         python open_test.py 0 250000        # 指定 channel / bitrate

import sys
import can

channel = int(sys.argv[1]) if len(sys.argv) > 1 else 0
bitrate = int(sys.argv[2]) if len(sys.argv) > 2 else 500000

print(f"python-can {can.__version__}  ->  open gs_usb channel={channel} bitrate={bitrate}")

try:
    bus = can.Bus(interface="gs_usb", channel=channel, bitrate=bitrate)
except Exception as e:
    print("\nOPEN FAILED:", repr(e))
    low = str(e).lower()
    if any(k in low for k in ("bit", "clock", "timing", "sample", "brp", "tseg", "sjw")):
        print("\n>> 已知坑：python-can 的 gs_usb 比特率换算只支持 48/80MHz 核心时钟")
        print("   (python-can #1747)。STM32C5 FDCAN2 核心时钟多半不是这俩。")
        print("   解法见 TEST_GUIDE.md §4 —— 把报错里的核心时钟值贴回去，我帮你把 FDCAN2 设成 48/80MHz。")
    elif any(k in low for k in ("no device", "not found", "could not find", "no matching")):
        print("\n>> 没找到 gs_usb 设备。检查：")
        print("   - 板子烧的是固件 A（gs_usb），不是 B（SLCAN）；")
        print("   - 设备管理器里 VID 1209:PID CA01 已加载 WinUSB（无黄色叹号），")
        print("     有叹号就用 Zadig 把它设成 WinUSB；")
        print('   - pip install "python-can[gs_usb]" 已装。')
    else:
        print("\n>> 未知错误，把上面整行贴回去。")
    sys.exit(1)

print("\nOPEN OK")
print("  channel_info:", getattr(bus, "channel_info", "n/a"))
print("\n通过：A 的设备端 + WinUSB/libusb + python-can 控制通道 OK（未发 CAN 帧）。")
print("下一步：连第二个 CAN 节点，跑 loop.py 验 TX/RX。")

try:
    bus.shutdown()
except Exception:
    pass
