#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
#
# 固件 A（gs_usb / CANnectivity）— 全面功能验证 + python-can 实践手册
# ===========================================================================
# 这个脚本既是验证工具，也是 python-can 的速成教材。每个子命令都注释讲清楚
# 对应的 python-can 概念。
#
# 用法：
#   python functional_check.py caps              # 1) 打开 + 打印设备能力
#   python functional_check.py monitor 5         # 2) 监听 5s：实时打印 + 存 capture.asc
#   python functional_check.py tx                # 3) 发一整套测试帧（标准/扩展/RTR/FD）
#   python functional_check.py throughput 500    # 4) 突发发 500 帧测速率+成功率
#   python functional_check.py filter 0x200 0x700 5  # 5) 硬件过滤后监听 5s
#   python functional_check.py all 3             # 顺序跑 caps->monitor->tx->throughput
#
# 前提：板子已烧固件 A；总线上有对端节点（CAN 发送要 ACK）。
# 安装：pip install python-can python-can-candle
#       （自带的 gs_usb 包经典-only，FD 帧会崩 struct.error；FD 走 candle 后端）

import sys
import time
import can

# python-can 的核心对象是 can.Bus —— 一切交互都从它开始。
# gs_usb 后端通过 libusb/WinUSB 跟设备说话（控制传输设参数 + 批量传输收发帧）。


# 用哪个 USB-CAN 后端：
#   "candle"  -> python-can-candle，支持 CAN FD（FD 必须用它；自带 gs_usb 经典-only 会崩）
#   "gs_usb"  -> python-can 自带，仅经典 CAN
INTERFACE = "candle"


def open_bus(bitrate=500000, data_bitrate=2000000, filters=None):
    """打开总线。
    - bitrate      : 名义相（arbitration）速率，classic 和 FD 都用。
    - data_bitrate : FD 数据相速率（BRS 帧用）；仅 candle 用得到。
    """
    if INTERFACE == "candle":
        bus = can.Bus(interface="candle", channel=0, fd=True,
                      bitrate=bitrate, data_bitrate=data_bitrate)
    else:
        bus = can.Bus(interface="gs_usb", channel=0, bitrate=bitrate)
    if filters:
        bus.set_filters(filters)  # 硬件/驱动层过滤，只放行匹配帧
    return bus


# ---------------------------------------------------------------------------
# 1) 能力探测
# ---------------------------------------------------------------------------
def cmd_caps():
    """打开设备，打印它报告的能力。先确认 FD 是否被支持、控制器就绪。"""
    bus = open_bus()
    print("=== gs_usb 设备 ===")
    print("  channel_info :", bus.channel_info)
    # protocol==CAN_FD(1) 表示设备支持 CAN FD；state 应为 ERROR_ACTIVE。
    print("  protocol     :", getattr(bus, "protocol", "n/a"),
          "(CAN_FD=1 才支持 FD)")
    print("  state        :", getattr(bus, "state", "n/a"))
    print("\n注：FD 是否真能用，以 `tx` 里 FD 帧是否 OK 为准。")
    bus.shutdown()


# ---------------------------------------------------------------------------
# 2) 监听（Notifier + Listener 模式 —— python-can 推荐的 RX 写法）
# ---------------------------------------------------------------------------
def cmd_monitor(duration=5):
    """Notifier 起一个后台线程跑 bus.recv()，把收到的 can.Message 分发给一组 Listener：
      - can.Printer()      -> 打到屏幕
      - can.Logger(p.asc)  -> 写文件（Vector ASC 格式，可拖进 SavvyCAN 回放）
    """
    bus = open_bus()
    print(f"=== 监听 {duration}s（同时写 capture.asc，可拖进 SavvyCAN）===")
    notifier = can.Notifier(bus, [can.Printer(), can.Logger("capture.asc")])
    time.sleep(duration)
    notifier.stop()
    bus.shutdown()
    print("--> capture.asc 已写。SavvyCanvas: File -> Load Vehicle / Bus Traffic -> ASC。")


# ---------------------------------------------------------------------------
# 3) TX 全套 —— 逐类验证发送通路
# ---------------------------------------------------------------------------
def cmd_tx():
    """发一整套代表性帧。gs_usb 的 bus.send() 是"等设备 TX 完成回调（=拿到 ACK）
    才返回"，所以没抛异常 = 真上了总线。"""
    bus = open_bus()

    def tx(label, msg):
        try:
            bus.send(msg, timeout=1.0)
            print(f"  OK   {label:22} {msg}")
        except can.CanError as e:
            print(f"  FAIL {label:22} {e}")

    print("=== TX 全套 ===")
    # can.Message 字段：arbitration_id, data, is_extended_id(29bit), is_fd, bitrate_switch(BRS),
    #                   is_remote_frame(RTR)。DLC 由 len(data) 决定（FD 支持 0..64 的非线性 DLC）。
    # 注意：is_extended_id 默认 True！标准帧必须显式写 False。
    tx("标准11bit 8B",       can.Message(arbitration_id=0x123, is_extended_id=False,
                                         data=b"\x11\x22\x33\x44\x55\x66\x77\x88"))
    tx("标准 0 字节",         can.Message(arbitration_id=0x100, is_extended_id=False))
    tx("扩展29bit 8B",       can.Message(arbitration_id=0x1ABCDE, is_extended_id=True,
                                         data=b"\xAA\xBB\xCC\xDD\xEE\xFF\x00\x11"))
    tx("标准 RTR",           can.Message(arbitration_id=0x200, is_extended_id=False,
                                         is_remote_frame=True))
    # CAN FD（固件 A 的卖点）：
    tx("FD 64B 无BRS",       can.Message(arbitration_id=0x555, data=bytes(64),
                                         is_fd=True, bitrate_switch=False))
    tx("FD 64B +BRS",        can.Message(arbitration_id=0x556, data=bytes(64),
                                         is_fd=True, bitrate_switch=True))
    tx("FD 12B(DLC=12)",     can.Message(arbitration_id=0x557, data=bytes(12), is_fd=True))
    bus.shutdown()
    print("注：FD+BRS 若 FAIL，多半是 data_bitrate 没设上（gs_usb 版本旧）；FD 无 BRS 一般都 OK。")


# ---------------------------------------------------------------------------
# 4) 吞吐 / 丢帧
# ---------------------------------------------------------------------------
def cmd_throughput(n=500):
    """突发发 n 帧，测真实速率和成功率。速率受 CAN 总线 + ACK 往返限制，
    不是主机 CPU。有 FAIL 说明总线拥堵或对端跟不上。"""
    bus = open_bus()
    print(f"=== 突发 TX {n} 帧 ===")
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
    print(f"  成功 {ok}/{n}，用时 {dt:.2f}s，速率 {ok / dt:.0f} 帧/s")
    bus.shutdown()


# ---------------------------------------------------------------------------
# 5) 过滤
# ---------------------------------------------------------------------------
def cmd_filter(can_id, mask, duration=5):
    """硬件过滤：只放行 (id & mask)==(can_id & mask) 的帧。mask=1 表示"关心该 bit"。
    例：filter 0x200 0x700 -> 只收 id 高3位==010 的帧（0x200..0x2FF）。"""
    bus = open_bus(filters=[{"can_id": can_id, "can_mask": mask, "extended": False}])
    print(f"=== 过滤 id&{mask:#x}=={can_id & mask:#x}，监听 {duration}s ===")
    end = time.time() + duration
    seen = 0
    while time.time() < end:
        msg = bus.recv(timeout=0.5)
        if msg:
            print("  ", msg)
            seen += 1
    print(f"  过滤后收到 {seen} 帧。")
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
