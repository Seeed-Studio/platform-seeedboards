# XIAO STM32C5 CAN FD 数据段压测固件（PSIS 100 MHz）

这是 `zephyr-canfd-data-stress` 的独立时钟配置变体，用于验证精确的
CAN FD 5 Mbit/s 数据段。`zephyr/app.overlay` 仅将 FDCAN 所使用的 PSIS
从 144 MHz 调整到 100 MHz；系统时钟仍保持板级 HSIS 的 144 MHz，因此可采用
`100 MHz / (BRP=1 * 20 TQ) = 5 Mbit/s`。

CPU/HCLK 不受此变体影响。请使用以下命令测试：

```text
cfd start tx 500000 5000000 64 30 0 fd-brs
```

这个固件用于 XIAO STM32C5 和图莫斯 UTA0504 USB2CANFD&LIN 适配器之间的 CAN FD 数据段测试。

第一阶段目标不是一次性测出极限，而是先跑通这条链路：

```text
XIAO STM32C5 CAN FD+BRS  <----100m CAN线---->  UTA0504  <----USB---->  TCANLINPro
```

测试重点是 CAN FD 的数据段。简单理解：

- 仲裁段：一帧 CAN 报文前半段，用来决定谁先发，速率通常较低，例如 500 kbps 或 1 Mbps。
- 数据段：CAN FD 报文真正搬运 payload 的部分，打开 BRS 后可以切到更高速率，例如 2 Mbps、5 Mbps、8 Mbps。
- BRS：Baud Rate Switch，表示这帧在数据段切换到高速率。

本固件默认发送标准 ID `0x504` 的 CAN FD+BRS 帧，payload 最多 64 bytes。

## 文件位置

- 固件主程序：`examples/seeed-xiao-stm32c5/zephyr-canfd-data-stress-psis100/src/main.c`
- Zephyr 配置：`examples/seeed-xiao-stm32c5/zephyr-canfd-data-stress-psis100/zephyr/prj.conf`
- 时钟覆盖：`examples/seeed-xiao-stm32c5/zephyr-canfd-data-stress-psis100/zephyr/app.overlay`
- PlatformIO 工程：`examples/seeed-xiao-stm32c5/zephyr-canfd-data-stress-psis100/platformio.ini`
- 板级 CAN 收发器配置：`zephyr/boards/seeed/xiao_stm32c5/xiao_stm32c5.dts`

## 硬件接线

CAN 测试只需要先接两根总线线：

```text
UTA0504 CAN_H  ----  XIAO CAN_H
UTA0504 CAN_L  ----  XIAO CAN_L
```

注意事项：

- 不要把 H/L 接反。接反通常会导致完全收不到帧，或者总线错误快速增加。
- 100m 线缆建议使用双绞线。
- 总线两端各需要一个 120 ohm 终端电阻，电阻跨接在 CAN_H 和 CAN_L 之间。
- UTA0504 端可以在 TCANLINPro 里勾选内置 120 ohm 终端电阻。
- XIAO 端如果板上没有 120 ohm，需要外接一个 120 ohm 电阻。
- 如果使用 DB9/HL-MHBJ9F01 这种 9 孔接头，必须先确认哪个孔是 CAN_H、哪个孔是 CAN_L。不要直接套用通用 DB9-CAN 线序。

XIAO 板上的 CAN 收发器 standby 脚已经在 devicetree 里配置给 Zephyr 管理。应用层不需要手动拉 STB，`can_start()` 会启用收发器。

## 固件能力

当前固件支持：

- CAN FD 模式：`CAN_MODE_FD`
- 仲裁段速率配置：`can_set_bitrate()`
- 数据段速率配置：`can_set_bitrate_data()`
- CAN FD+BRS 发送：`CAN_FRAME_FDF | CAN_FRAME_BRS`
- payload 长度选择，数据段测试建议优先用 64 bytes
- 三种模式：`tx`、`rx`、`bidi`
- `fps=0` 满速发送，或指定目标 fps
- payload 内写入 magic、sequence、timestamp、pattern
- 统计 TX 成功、TX 入队失败、RX 数、sequence gap、内容错误
- 每秒打印统计，测试结束打印 summary
- 启用 `CONFIG_CAN_STATS`，输出 bit/stuff/crc/form/ack/rx-overrun 等 CAN 错误统计

当前固件不做：

- 自动扫频。
- 自动控制 TCANLINPro。
- 自动判断 100m 线缆的最高可靠速率。
- 上位机日志文件解析。

这些可以在当前 shell 命令框架上继续扩展。

## 编译和烧录

进入工程目录：

```powershell
cd D:\workspace\platform-seeedboards\examples\seeed-xiao-stm32c5\zephyr-canfd-data-stress-psis100
```

编译：

```powershell
pio run -v
```

烧录后执行 `cfd clock`，应打印 `can_core_clock=100000000 Hz`，再执行本文开头的 5 Mbit/s 命令。

固件产物通常在：

```text
.pio\build\seeed-xiao-stm32c5\firmware.uf2
.pio\build\seeed-xiao-stm32c5\firmware.hex
.pio\build\seeed-xiao-stm32c5\firmware.elf
```

烧录方式按当前板子的调试/UF2流程执行即可。

## 串口 Shell

烧录后打开串口，波特率：

```text
115200
```

启动后会看到类似：

```text
XIAO STM32C5 CAN FD data phase stress
Use shell command: cfd start tx 500000 2000000 64 30 0 fd-brs
```

固件不会上电自动压测，需要手动输入 shell 命令。

命令格式：

```text
cfd start <tx|rx|bidi|loop> [nominal_bitrate] [data_bitrate] [payload_bytes] [duration_s] [fps] [can|fd|fd-brs]
cfd status
cfd stop
cfd clock
cfd regs
```

参数解释：

| 参数 | 含义 | 示例 |
| --- | --- | --- |
| `tx` | XIAO 只发送，UTA0504/上位机接收显示 | `cfd start tx ...` |
| `rx` | XIAO 只接收，UTA0504 负责发送 | `cfd start rx ...` |
| `bidi` | XIAO 一边发送一边接收，配合 UTA0504 同时发送 | `cfd start bidi ...` |
| `loop` | XIAO 进入 CAN FD loopback，主要用于排查 MCU 控制器和时钟，不用于测 UTA0504 | `cfd start loop ...` |
| `nominal_bitrate` | 仲裁段速率 | `500000` |
| `data_bitrate` | 数据段速率 | `2000000` |
| `payload_bytes` | 数据长度，CAN FD 最大 64 | `64` |
| `duration_s` | 测试时长，秒 | `30` |
| `fps` | 目标发送帧率，`0` 表示尽可能满速 | `0` |
| `can` | Classic CAN 帧，最大 8 字节，用于先排查基础 CAN 物理链路和 ACK | `cfd start tx 500000 0 8 30 100 can` |
| `fd` | CAN FD 帧但不带 BRS，数据段不切高速 | `cfd start tx 500000 500000 64 30 100 fd` |
| `fd-brs` | CAN FD + BRS，当前压测默认模式 | `cfd start tx 500000 2000000 64 30 0 fd-brs` |

诊断命令：

```text
cfd clock
cfd regs
```

- `cfd clock`：打印 Zephyr `can_get_core_clock()` 返回的 CAN 内核时钟。本变体期望 FDCANSEL 为 `1`（PSIS），且时钟为 `100000000 Hz`。
- `cfd regs`：按 STM32C5/Bosch M_CAN 的正确寄存器偏移打印 FDCAN 和 RCC 关键寄存器。注意 `0x4000A400 + 0x00` 是 `CREL`，真正的 `CCCR` 是 `0x4000A400 + 0x18`。

如果 `cfd start tx 500000 2000000 64 30 0` 仍然在 `can_start` 返回 `-11`，固件会自动打印一组 `fail ...` 诊断寄存器。

建议当前故障优先这样试：

```text
cfd regs
cfd start loop 500000 0 8 5 100 can
cfd start tx 500000 0 8 30 100 can
cfd start loop 500000 2000000 64 5 100
cfd start tx 500000 1000000 64 5 100
cfd start tx 500000 2000000 64 30 0
```

`loop` 能启动但 `tx` 启动失败时，优先怀疑外部 CAN 总线没有保持空闲，例如 CAN_H/CAN_L 接反、终端电阻不对、UTA0504 端口/通道没停好、收发器 STB 极性或接线问题。`loop` 也失败时，优先看 `cfd regs` 里的 `CCIPR1/FDCANSEL/CKDIV/CCCR`。

## 建议的第一轮测试

先不要直接上 8 Mbps。建议按这个顺序逐步确认：

```text
cfd start tx 500000 0 8 30 100 can
cfd start tx 500000 500000 64 30 100 fd
cfd start tx 500000 1000000 64 30 100
cfd start tx 500000 2000000 64 30 0
cfd start tx 500000 4000000 64 30 0
cfd start tx 500000 5000000 64 30 0
```

确认每档 TCANLINPro 都能正常显示 64 字节 CAN FD 帧后，再继续尝试：

```text
cfd start tx 500000 6000000 64 30 0
cfd start tx 500000 8000000 64 30 0
```

如果要测 8 Mbps，板级 devicetree 中 CAN transceiver 的 `max-bitrate` 必须允许 `8000000`：

```dts
max-bitrate = <8000000>;
```

## TCANLINPro 配合使用

### 1. 连接设备

1. 用 USB 连接 UTA0504 到电脑。
2. 打开 TCANLINPro。
3. 进入设备管理页面。
4. 如果没有自动识别设备，点击扫描设备。
5. 选择 UTA0504 对应设备和 CAN 通道，通常先用 CAN1。

图莫斯官方文档入口：

- UTA0504 产品页：<http://www.toomoss.com/product/17-cn.html>
- TCANLINPro 下载页：<http://www.toomoss.com/download/7-cn.html>
- 帮助文档入口：<http://www.toomoss.com/help/index.htm>
- 启动 CAN 总线教程：<http://www.toomoss.com/help/topics/软件使用/TCANLINPro软件使用教程/启动CAN总线.htm>
- 普通 CAN 视图教程：<http://www.toomoss.com/help/topics/软件使用/TCANLINPro软件使用教程/普通CAN视图.htm>

### 2. 配置 CAN FD 总线

TCANLINPro 里需要和 MCU 侧参数完全一致：

| 项目 | 建议值 |
| --- | --- |
| 总线类型 | CAN FD |
| CAN FD 格式 | ISO CAN FD，若有该选项 |
| BRS | 开启 |
| 仲裁段/标称速率 | 和 `nominal_bitrate` 一致，例如 `500000` |
| 数据段速率 | 和 `data_bitrate` 一致，例如 `2000000` |
| 终端电阻 | UTA0504 位于总线一端时勾选 120 ohm |
| 工作模式 | 正常模式，不要用 silent/listen-only 做发送测试 |
| 通道 | 接线使用 CAN1 就选 CAN1 |

最容易出错的是这三个：

- MCU 和 TCANLINPro 的仲裁段速率不一致。
- MCU 和 TCANLINPro 的数据段速率不一致。
- MCU 发的是 FD+BRS，但上位机没有开启 CAN FD 或 BRS。

### 3. 上位机接收 XIAO 发送帧

这是第一阶段最重要的测试。

TCANLINPro：

1. 启动 CAN 总线。
2. 打开普通 CAN 视图。
3. 开始接收/显示。

XIAO 串口输入：

```text
cfd start tx 500000 2000000 64 30 0
```

TCANLINPro 应看到：

- ID 为 `0x504` 的帧。
- 帧类型是 CAN FD。
- BRS 开启。
- DLC 对应 64 bytes。
- 数据不断变化。

payload 前 12 字节含义：

| 字节位置 | 含义 |
| --- | --- |
| `0..3` | magic，固定标记，用于识别本测试帧 |
| `4..7` | sequence，小端序，每帧递增 |
| `8..11` | timestamp，MCU 的 `k_uptime_get_32()` |
| `12..63` | pattern，用于内容检查 |

TCANLINPro 能稳定显示这些帧，说明 XIAO 到 UTA0504 的数据段接收路径已经跑通。

### 4. XIAO 接收 UTA0504 发送帧

TCANLINPro 侧新建普通发送帧：

| 项目 | 建议值 |
| --- | --- |
| 帧类型 | CAN FD |
| BRS | 开启 |
| ID | 可以用 `0x504`，也可以用其他标准 ID |
| 数据长度 | 64 bytes |
| 发送方式 | 周期发送 |
| 周期 | 先从 10 ms 或 100 ms 开始 |

XIAO 串口输入：

```text
cfd start rx 500000 2000000 64 30 0
```

观察 XIAO 串口每秒统计：

```text
stat t=... rx=... checked=... unchecked=... gap=... content_err=... state=active rxerr=0 txerr=0
```

说明：

- `rx` 增加：XIAO 收到了帧。
- `checked` 增加：收到的是本固件格式的测试帧。
- `unchecked` 增加：收到了其他格式帧，通常不代表错误。
- `content_err` 增加：payload pattern 不符合本固件格式。
- `rxerr/txerr` 增加：物理层、波特率、终端电阻、线缆质量可能有问题。

如果 TCANLINPro 发送的是手工任意数据，`unchecked` 增加是正常的。只有它也按本固件 payload 格式发送，`checked` 才会增加。

### 5. 双向/并发测试

TCANLINPro 开启周期发送，同时 XIAO 也发送：

```text
cfd start bidi 500000 2000000 64 30 0
```

这时要同时观察两边：

- TCANLINPro 是否继续正常显示 XIAO 发出的 `0x504` CAN FD+BRS 帧。
- XIAO 串口的 `rx` 是否持续增长。
- XIAO 串口的 `state` 是否保持 `active`。
- `ack/crc/form/stuff/rx_overrun` 是否增长。

双向测试比单向更容易暴露问题，因为总线负载、PC 上位机显示速度、USB 传输、软件刷新都会参与进来。

## 统计输出怎么看

固件每秒输出一行 `stat`，结束时输出 `summary`。

示例：

```text
stat t=5s mode=tx nominal=500000 data=2000000 len=64 tx_ok=1234 tx_fail=0 tx_cb_err=0 rx=0 checked=0 unchecked=0 gap=0 content_err=0 tx_Bps=15795 rx_Bps=0 state=active rxerr=0 txerr=0
can_stats bit=0 bit0=0 bit1=0 stuff=0 crc=0 form=0 ack=0 rx_overrun=0
```

字段解释：

| 字段 | 含义 |
| --- | --- |
| `tx_ok` | CAN 驱动确认发送完成的帧数 |
| `tx_fail` | 发送入队失败，满速时如果偶发不一定立刻代表总线错误 |
| `tx_cb_err` | TX callback 返回错误 |
| `rx` | 收到的总帧数 |
| `checked` | 收到并识别为本测试格式的帧数 |
| `unchecked` | 收到但不是本测试格式的帧数 |
| `gap` | sequence 不连续次数/缺口估算 |
| `content_err` | payload pattern 检查错误 |
| `tx_Bps/rx_Bps` | payload 字节吞吐，不包含 CAN 帧开销 |
| `state` | CAN 控制器状态，正常应为 `active` |
| `rxerr/txerr` | CAN 控制器错误计数 |
| `ack` | ACK 错误，常见原因是总线上没有其他节点确认 |
| `crc/form/stuff` | 常见于速率不匹配、线缆/终端/信号质量问题 |
| `rx_overrun` | MCU 接收处理不过来或队列溢出 |

## 测试建议流程

第一轮只验证链路：

```text
cfd start tx 500000 1000000 64 30 100
```

第二轮验证数据段高速：

```text
cfd start tx 500000 2000000 64 30 0
cfd start tx 500000 4000000 64 30 0
cfd start tx 500000 5000000 64 30 0
```

第三轮验证 100m 极限：

```text
cfd start tx 500000 6000000 64 60 0
cfd start tx 500000 8000000 64 60 0
```

第四轮再做双向：

```text
cfd start bidi 500000 2000000 64 60 0
cfd start bidi 500000 4000000 64 60 0
```

每一轮都记录：

- 线长。
- 终端电阻配置。
- 仲裁段速率。
- 数据段速率。
- payload bytes。
- 测试时长。
- XIAO `summary`。
- TCANLINPro 是否持续正常显示。
- TCANLINPro 是否有丢帧、错误、卡顿或日志异常。

## 图莫斯上位机和固件的能力边界

固件侧适合做：

- 真实发送和接收。
- 统计 MCU 看到的 RX/TX 数量。
- 检查 sequence gap 和 payload 内容。
- 读取 CAN 控制器状态和错误计数。

TCANLINPro 适合做：

- 配置 UTA0504 CAN FD 参数。
- 显示总线上收到的帧。
- 手动或周期发送 CAN/CAN FD 帧。
- 导出日志，作为测试证据。

不要只用 TCANLINPro 的界面刷新速度判断总线极限。高速 CAN FD 满载时，GUI 显示、USB、PC 性能、日志写盘都可能先成为瓶颈。极限速率判断应以固件统计、CAN 错误计数、上位机日志三者一起看。

## 常见问题

### TCANLINPro 完全收不到 XIAO 的帧

优先检查：

- CAN_H/CAN_L 是否接反。
- 两端是否都有 120 ohm 终端。
- TCANLINPro 是否启动了正确的 CAN 通道。
- TCANLINPro 是否打开 CAN FD 和 BRS。
- 仲裁段速率、数据段速率是否和固件命令一致。
- XIAO 串口是否显示 `state=active`。

### XIAO 一直出现 ACK 错误

常见原因是总线上没有另一个正常工作的 CAN 节点回应 ACK。检查 UTA0504 是否已经启动 CAN 总线，并且速率匹配。

### 低速能通，高速不通

常见原因：

- 100m 线缆信号质量不够。
- 终端电阻位置或阻值不对。
- 数据段采样点不合适。
- TCANLINPro 和 MCU 的 data bitrate 不一致。
- 实际使用的 board devicetree 仍限制 `max-bitrate = <5000000>`。

### `checked` 不增长，但 `rx` 增长

说明 XIAO 收到了帧，但 payload 不是本固件定义的格式。TCANLINPro 手动发送任意数据时，这是正常现象。

### `pio run` 最后显示 `buildprog Error 1`

当前环境里观察到普通 `pio run` 可能在 UF2 已生成后，由 platform 的后处理目标返回 `Error 1`。可以使用：

```powershell
pio run -v
```

当前该命令已验证可成功完成。

### 输入文档里的命令后提示 `invalid nominal bitrate`

这是早期固件中的参数解析问题：`shell_strtoul()` 的错误变量没有初始化，导致 `500000` 这类合法数字也可能被误判为错误。

修复后需要重新编译并烧录最新固件。如果串口仍然提示：

```text
invalid nominal bitrate
```

基本说明板子里跑的还是旧固件。
