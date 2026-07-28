# XIAO STM32C5 gs_usb 桥（固件 A / CANnectivity）— 使用与测试指南

把 XIAO STM32C5 变成一个 **gs_usb** USB-CAN 适配器（CANnectivity 固件）。
设备以 vendor-class USB 出现：**VID `0x1209` : PID `0xCA01`**（pid.codes，Linux
内核 `gs_usb` 驱动自动绑定；Windows 经 WCID 自动加载 WinUSB）。

> **Windows vs Linux 现实**：A 的"主场"是 **Linux 原生 SocketCAN**（`modprobe gs_usb`
> → `can0`，任意时钟都能算比特率，SavvyCAN 也能经 SocketCAN 用）。Windows 上没有
> SocketCAN/内核 gs_usb，**只能靠 python-can 的 `gs_usb` 后端**（经 WinUSB），而且
> 有一个**比特率时钟坑**（见 §4）。SavvyCAN 在 Windows 上**连不了 A**。

---

## 0. 是什么 / 不是什么

- **是**：gs_usb vendor-class USB-CAN，支持 **CAN FD**（最高 8Mbps 数据相）。
  原生 SocketCAN（Linux）+ python-can（全平台）。
- **不是**：串口/SLCAN（那是固件 B）。A 占用 USB vendor-class，**没有 CDC 串口**，
  所以 1200bps UF2 触发不适用，烧录用双击 RESET。
- Windows 上 A **只能用 python-can**（不能 SavvyCAN）。

---

## 1. 前置（Windows）

```powershell
pip install "python-can[gs_usb]"
# 这会装 python-can + gs_usb 包（jxltom/gs_usb，内含 libusb 绑定）
```
- 一根数据 USB 线。
- CAN 收发测试（Tier 2）需要**第二个 CAN 节点**（另一块 XIAO / CAN 分析仪 /
  达妙电机），CANH/CANL + 120Ω 终端 + 共地。

---

## 2. 构建与烧录

```bash
cd examples/seeed-xiao-stm32c5/zephyr-can-bridge-gsusb
pio run                   # 产出 firmware.uf2（本机平台 symlink，见 platformio.ini 注释）
```
烧录：**双击 RESET** → 进入 `XIAOC5BOOT` 卷 → 把
`.pio/build/seeed-xiao-stm32c5/firmware.uf2` 拖进去。
（A 占用 USB，`pio run -t upload` 的 1200bps 触发不可用。）

插上后，Windows 设备管理器里应出现一个 **VID 1209 / PID CA01** 的设备，自动用
**WinUSB** 驱动（无黄色叹号）。

> 如果出现黄色叹号（驱动没自动加载，旧版 Windows 偶发）：用 [Zadig](https://zadig.akeo.ie/)
> 把 VID 1209:CA01 的接口驱动设成 **WinUSB**（替换/安装），再继续。

---

## 3. Tier 1 — 枚举 + python-can 打开（无需 CAN 对端）

这一步验 **USB vendor-class 设备端 + WinUSB + python-can 控制通道**，不发 CAN 帧、
不需要对端。运行：

```python
# open_test.py
import can
try:
    bus = can.Bus(interface='gs_usb', channel=0, bitrate=500000)
    print("OPEN OK ->", bus.channel_info)
    bus.shutdown()
except Exception as e:
    print("OPEN FAILED:", repr(e))
    s = str(e).lower()
    if any(k in s for k in ("bit", "clock", "timing", "sample", "brp", "tseg")):
        print(">> 这是 §4 的比特率时钟坑（核心时钟不是 48/80MHz）。跳到 §4。")
    elif any(k in s for k in ("no device", "not found", "find")):
        print(">> 没找到设备。检查 §2 的 WinUSB 枚举 / VID:PID。")
```

**通过判据**：`OPEN OK` 打印出 `channel_info`（含 gs_usb 设备信息）。到这步证明
A 的设备端在 Windows 上通了。

> 注意：`bitrate=500000` 在打开时就会发 BITTIMING，如果命中 §4 的时钟坑，**这一步
> 就会 FAIL**。所以先看 §4 心里有数。

---

## 4. ⚠️ Windows 头号坑：比特率只支持 48/80MHz 核心时钟

python-can 的 gs_usb 实现**只对 48MHz 和 80MHz 的 CAN 核心时钟写死了比特率换算**
（[python-can #1747](https://github.com/hardbyte/python-can/issues/1747)）。我们
STM32C5 的 FDCAN2 核心时钟不一定是这俩。如果 `bitrate=500000` 打开时报 bit/timing
相关错误，就是这个原因。

**怎么确认核心时钟值**：python-can 的报错或 `bus.channel_info` 里通常会带 gs_usb
回报的 `btconst`/`fclk_can`（核心时钟 Hz）。把这个值贴我。

**三种缓解（按推荐度）**：

1. **改在 Linux 验证 A**（最省事）：Linux 内核的 gs_usb 驱动对**任意**核心时钟都能
   正确算 bittiming（用内核的 CAN bittiming 计算器）。`ip link set can0 up type
   can bitrate 500000` 直接成。A 本来就是为 Linux 原生 SocketCAN 设计的——见 §5。
2. **把 STM32C5 的 FDCAN2 核心时钟设成 48 或 80 MHz**（overlay + 重烧），这样
   python-can 的 48/80 换算就适用。这个我可以帮你改（需要确认板子可用的时钟源）。
3. **升级 `gs_usb` / `python-can` 到支持任意时钟的版本**（若上游已修 #1747）。

> 这也是为什么 **B 更适合 Windows 先验证**：B 的 SLCAN 比特率是固件自己用
> Zephyr 的 `can_set_bitrate` 设的（支持任意时钟），不经过 python-can 的 48/80 限制。

---

## 5. Tier 2 — CAN 收发（需要第二个 CAN 节点）

经典 CAN 发送必须有对端回 ACK，单节点会 bus-off。所以 TX/RX 必须有对端
（第二块 XIAO / CAN 分析仪 / 电机）。

### Windows：python-can gs_usb

```python
# loop.py  （需要 CAN 对端；对端在发才能 recv 到）
import can, time
bus = can.Bus(interface='gs_usb', channel=0, bitrate=500000)
print("opened:", bus.channel_info)

# 发一帧（需要对端 ACK）
bus.send(can.Message(arbitration_id=0x123, data=[0xDE,0xAD,0xBE,0xEF],
                      is_extended_id=False))
print("sent 0x123#DEADBEEF")

# 收（对端在发才行）
msg = bus.recv(timeout=2.0)
print("recv:", msg)

# CAN FD 帧示例（A 支持 FD；数据相速率见你的总线配置）
# bus.send(can.Message(arbitration_id=0x456, data=bytes(range(64)),
#                       is_fd=True, bitrate_switch=True))
bus.shutdown()
```

CAN FD：A 支持。`can.Message(..., is_fd=True, bitrate_switch=True, data=64字节)`。

---

## 6. Linux 路径（A 的主场，最顺）

A 在 Linux 上是**原生 SocketCAN**——这是它相对 B 的最大价值，也是避开 §4 时钟坑
的最干净办法：

```bash
sudo modprobe gs_usb                 # 通常已自动加载；VID 1209:CA01 在内核 id_table
ip link                              # 应看到 can0
sudo ip link set can0 up type can bitrate 500000   # 内核算 bittiming，任意时钟都行
candump -i can0                      # 收
cansend can0 123#DEADBEEF            # 发
# CAN FD:
# sudo ip link set can0 up type can bitrate 500000 dbitrate 2000000 fd on
```

**SavvyCAN（仅 Linux）**：Connection → SocketCAN → `can0`。Windows 上 SavvyCAN
连不了 A。

---

## 7. 故障排查

| 现象 | 原因 / 处理 |
|---|---|
| 设备管理器黄色叹号 | WinUSB 没自动加载 → Zadig 把 1209:CA01 设成 WinUSB。 |
| python-can "no device / not found" | VID:PID 没被 gs_usb 包识别；或驱动没装成 WinUSB；或板子没烧 A（烧的是 B 就没有这个设备）。 |
| 打开报 bit/timing/clock 错 | **§4 时钟坑**。确认核心时钟值，按 §4 缓解。 |
| `OPEN OK` 但 `send` 后无 ACK / bus-off | 单节点无对端。加第二个 CAN 节点。 |
| 收发完全不通 | ① 收发器 standby(PB14)；② 两端波特率不一致；③ CANH/CANL 接反；④ 缺 120Ω 终端；⑤ 没共地。 |
| 想要无硬件的 CAN 自测 | A 不像 B 有串口回环握手；gs_usb 的 loopback 模式 python-can 暴露有限。建议改在 Linux 用 `ip link ... type can` + 自收自发，或临时把 CANnectivity 设 loopback（进阶）。 |

## 8. 已知限制 & 与 B 的对比

| | 固件 A（gs_usb） | 固件 B（SLCAN） |
|---|---|---|
| Windows 验证 | python-can（WinUSB）；有 §4 时钟坑 | 串口 + SavvyCAN/python-can，无时钟坑 |
| Linux 验证 | 原生 SocketCAN `can0`（最顺） | `slcand` 转 SocketCAN |
| SavvyCAN | 仅 Linux | 全平台（Lawicel） |
| CAN FD | ✅ 支持 | ❌ 仅 classic CAN |
| 免驱 | Linux 内核 gs_usb；Windows WCID WinUSB | 串口，全平台免驱 |
| 单板无硬件自测 | 较难（无串口回环） | ✅ `V→V1013` + loopback 模式 |

**建议**：Windows 上**先用 B 把链路验通**（最容易），A 的真实验证放到 Linux
（原生 SocketCAN，避开时钟坑）最省心；Windows 上验证 A 主要确认枚举 + python-can
能开，CAN 收发若撞 §4 就按缓解处理。
