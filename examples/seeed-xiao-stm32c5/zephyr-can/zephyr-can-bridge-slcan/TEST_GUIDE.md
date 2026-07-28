# XIAO STM32C5 SLCAN 桥（固件 B）— 使用与测试指南

把 XIAO STM32C5 变成一个 USB-CAN 适配器，主机端通过 USB CDC ACM 串口说
Lawicel **SLCAN** 协议。一份固件通吃三类主机工具，全平台免驱。

> **为什么 B 最容易通过校验**：SLCAN 是"请求-应答"的串口文本协议，CDC ACM
> 串口在 Win/Mac/Linux 插上即识别（板子以 Seeed VID `0x2886:0x00C5` 枚举成
> 普通 /dev/ttyACMx 或 COMx）。而且**不需要任何 CAN 对端节点**就能验通
> "CDC 收 → 解析 → 回复 → CDC 发"整条链路（见下方 Tier 1）。CAN 收发才需要
> 第二个节点或回环模式。

---

## 0. 这版固件是什么 / 不是什么

- **是**：Classic CAN 的 USB↔CAN 桥，FDCAN2（PB5/PB13，板载收发器，standby=PB14）。
- **不是**：CAN FD（Lawicel SLCAN 没有 FD 标准帧格式）。要 FD 用固件 A（gs_usb）。
- **不是**：原生 SocketCAN。要原生 SocketCAN 用固件 A；B 在 Linux 上要靠
  `slcand` 把串口转成 SocketCAN。
- 单路 CAN（FDCAN2）。FDCAN1（PB8/PB9）本版未用。

---

## 1. 前置

- 一块 XIAO STM32C5（已刷本固件）。
- 一根 **数据线** USB（注意别用只能充电的线）。
- 主机：Python 3 + `pyserial`、`python-can`（`pip install pyserial python-can`）；
  或任意串口工具（`pio device monitor` / `screen` / PuTTY / 串口调试助手）。
- **CAN 收发测试**（Tier 2）还需要：第二个 CAN 节点（另一块 XIAO 跑
  `can-counter` / `can-simple-rx`，或达妙电机，或别的 CAN 分析仪），以及
  CANH/CANL 连线 + 总线两端各一个 120Ω 终端电阻 + 共地。

## 2. 构建与烧录

```bash
cd examples/seeed-xiao-stm32c5/zephyr-can-bridge-slcan
pio run                   # 产出 firmware.uf2
pio run -t upload         # 烧录（1200bps CDC 触发，或双击 RESET）
```
B 带 CDC ACM，所以 `pio run -t upload` 的 1200bps 自动触发可用；也可以手动
双击 RESET 进入 `XIAOC5BOOT` 卷，把 `.pio/build/seeed-xiao-stm32c5/firmware.uf2`
拖进去。

烧好后板子枚举成一个串口：Linux `/dev/ttyACMx`，Windows `COMx`，macOS
`/dev/cu.usbmodem*`。

---

## 3. Tier 1 — 独立串口冒烟测试（无需 CAN 硬件）⭐ 核心

这一步只验 **CDC↔SLCAN 解析↔回复** 这条链路，不碰 CAN 总线，最快、最干净。
直接跑下面这个 Python 脚本（明确的 PASS/FAIL，没有人眼歧义）：

```python
# smoke.py  —  用法: python smoke.py [/dev/ttyACM0 | COM3]
import serial, time, sys
port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyACM0'
s = serial.Serial(port, 115200, timeout=0.5)
time.sleep(1)  # 等 CDC 稳定

def cmd(c):
    s.reset_input_buffer()
    s.write(c.encode() + b'\r')   # SLCAN 行以 CR 结尾
    time.sleep(0.15)
    return s.read(64)

checks = [
    ('V',  b'V1013\r'),   # 版本
    ('N',  b'N0001\r'),   # 序列号
    ('F',  b'F00\r'),     # 状态标志
    ('S6', b'\r'),        # 设 500kbps（S6=500k）→ 成功回 CR
    ('O',  b'\r'),        # 上线(on-bus) → 成功回 CR（无需对端）
    ('C',  b'\r'),        # 下线(off-bus)
]
ok = True
for c, exp in checks:
    got = cmd(c)
    passed = (got == exp)
    ok = ok and passed
    print(f"{'PASS' if passed else 'FAIL'}  {c!r:>5} -> {got!r}  (expect {exp!r})")
print('\n=== ALL PASS ===' if ok else '\n=== FAILURES ===')
s.close()
```

**通过判据**：6 项全 PASS。到这一步就证明固件 B 的 CDC + SLCAN 解析 + CAN
配置（bitrate/open/close）路径全通——**B 基本算通过校验**。

> 说明：SLCAN 成功应答就是一个 `\r`（0x0D），出错是 `BEL`（0x07，可能响一声）。
> 所以手动用串口工具测时，"看到回 CR / 空行" 即为成功；用脚本测最没歧义。

---

## 4. Tier 1.5 — 单板全链路自测（CAN 回环，仍无需 CAN 硬件）

想连"CAN 收发"也单板验掉？临时把固件切到 CAN 回环模式：把 `src/main.c` 里

```c
ret = can_set_mode(can_dev, CAN_MODE_NORMAL);
```
改成
```c
ret = can_set_mode(can_dev, CAN_MODE_LOOPBACK);
```

重新 `pio run -t upload`。回环模式下控制器把自己发的帧环回到接收，**不需要
外部 ACK、不需要总线、不需要第二个节点**。然后：

```bash
# 开串口，先发 S6\r O\r 上线，再发一帧：
S6<CR>O<CR>t1234DEADBEEF<CR>
# 期望先收到一个 \r（发送成功），紧接着收到 t1234DEADBEEF\r（回环收到的帧）
```

或用脚本：
```python
# loopback.py
import serial, time
s = serial.Serial('/dev/ttyACM0', 115200, timeout=0.5); time.sleep(1)
def cmd(c):
    s.reset_input_buffer(); s.write(c.encode()+b'\r'); time.sleep(0.2); return s.read(128)
print('S6 ->', cmd('S6').__repr__())      # \r
print('O  ->', cmd('O').__repr__())       # \r
print('tx ->', cmd('t1234DEADBEEF').__repr__())
# 期望 tx 回: b'\rt1234DEADBEEF\r'  （先发送ACK，再回环帧）
```
验完记得改回 `CAN_MODE_NORMAL` 再重新烧（否则真总线上发不出去）。

---

## 5. Tier 2 — 真实 CAN 收发（需要第二个 CAN 节点）

经典 CAN 是多主总线，**发送必须有另一个节点回 ACK**，否则单节点会一直重传
直到 bus-off。所以 TX/RX 测试必须有对端。

### 方式 A：Linux `slcand` → 原生 SocketCAN

```bash
# -s6 = 500kbps（对应固件 S6）。波特率表见末尾。
sudo slcand -o -s6 -c /dev/ttyACM0 can0
sudo ip link set can0 up
candump -i can0               # 收（对端在发就能看到）
cansend can0 123#DEADBEEF     # 发（id=0x123, data=DE AD BE EF）
# 用完： sudo ip link set can0 down && sudo slcand -k can0
```

### 方式 B：python-can（slcan 后端，跨平台）

```python
import can
# 创建时自动发 S6(500k) + O 上线
bus = can.Bus(interface='slcan', channel='/dev/ttyACM0', bitrate=500000)

# 发一帧（需要对端节点 ACK）
bus.send(can.Message(arbitration_id=0x123, data=[0xDE,0xAD,0xBE,0xEF],
                      is_extended_id=False))

# 收（对端在发才行，比如另一块 XIAO 跑 can-counter）
msg = bus.recv(timeout=2.0)
print(msg)

bus.close()   # 自动发 C 下线
```

### 方式 C：对端用第二块 XIAO

第二块 XIAO 刷 `examples/.../zephyr-can-counter`（它会周期性发
id=0x10 和 ext 0x12345）。两块板的 CANH/CANH、CANL/CANL 互连，共地，总线
至少一端加 120Ω。B 这边 `O` 上线后，串口会持续吐 `tiiildd\r` 收到的帧。

---

## 6. SavvyCAN（GUI，全平台）

1. 装 SavvyCAN。
2. **Connections → Add New Connection → Lawicel / SLCAN**。
3. 选板子的串口（COMx / ttyACMx），波特率按串口填（如 115200，CDC 下实际
   不影响数据）、CAN 比特率选 500k。
4. 连接。SavvyCAN 会自动发 S+O；总线有帧就在主界面看到，也能在 "Send Frames"
   里发帧。

> SavvyCAN 的 Lawicel 连接在 Win/Mac/Linux 都能用——这正是固件 B 相对 A 的
> 价值：A 的 SavvyCAN 只在 Linux（经 SocketCAN）能用。

---

## 7. SLCAN 命令参考（本固件实现）

CR 结尾（`\r`，也接受 `\n`）；命令字母不区分大小写（固件内部转大写）。

| 命令 | 含义 | 成功应答 | 说明 |
|---|---|---|---|
| `S0`..`S8` | 设 CAN 比特率预设 | `\r` | 见下表 |
| `O` | 上线（on-bus） | `\r` | 调 `can_start` |
| `C` | 下线（off-bus） | `\r` | 调 `can_stop` |
| `tiiildd` | 发标准 11-bit 帧 | `\r` | i=3 hex ID，l=1 hex DLC，dd=数据 |
| `TiiiiiiiiLdd` | 发扩展 29-bit 帧 | `\r` | 8 hex ID |
| `riiiL` / `RiiiiiiiiL` | 发 RTR | `\r` | 无数据 |
| `V` | 固件版本 | `V1013\r` | |
| `N` | 序列号 | `N0001\r` | |
| `F` | 状态标志 | `F00\r` | |
| `Z1`/`M`/`m`/`L`/`l` | 时间戳/验收滤波/只听 | `\r` | 应答但不实现，保持 accept-all |

**接收帧**：固件把收到的帧原样吐回——标准帧 `tiiildd\r`、扩展帧
`TiiiiiiiiLdd\r`、RTR `riiiL\r` / `RiiiiiiiiL\r`。

**比特率预设表**（Lawicel 标准）：

| 命令 | kbps | | 命令 | kbps |
|---|---|---|---|---|
| `S0` | 10 | | `S5` | 250 |
| `S1` | 20 | | `S6` | 500（默认） |
| `S2` | 50 | | `S7` | 800 |
| `S3` | 100 | | `S8` | 1000 |
| `S4` | 125 | | | |

---

## 8. 故障排查

| 现象 | 可能原因 / 处理 |
|---|---|
| 串口不出现 | 数据线？换口？板子是否跑的是 app（没卡在 bootloader）？重刷。 |
| `V` 无应答 | 主机没真正"打开"串口（要置 DTR）；端口选错；固件没烧成功。 |
| `O` 后发 `t...` 回 `BEL` 或卡住 | **单节点无 ACK**：总线上没有别的节点。加对端，或用 Tier 1.5 回环模式自测。 |
| 完全收发不通 | ① 收发器 standby（PB14）没被拉到 normal——板子 `can_phy0` 的 `phys` 绑定应自动处理，否则怀疑这块；② 两端波特率不一致（默认 S6=500k）；③ CANH/CANL 接反；④ 缺 120Ω 终端电阻；⑤ 两板没共地。 |
| 偶发丢帧 | USB 全速（12Mbps）吞吐上限约 1MB/s，经典 CAN 一般够；高负载才需关注。 |

## 9. 已知限制

- 仅 Classic CAN（8 字节数据）。CAN FD 走固件 A。
- 单路 CAN（FDCAN2）。
- 无硬件时间戳（`Z1` 应答但未实现）。
- 验收滤波为 accept-all（`M`/`m` 应答但未实现）。
- CDC 吞吐受 USB 全速上限约束。
