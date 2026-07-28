# XIAO STM32C5 两板直连 CAN 往返测试（Two-Board Round-Trip, USB CDC 版）

把**两块 XIAO STM32C5**直接对接测 CAN/CAN FD，**不接 USB-CAN 适配器**。
两块板子都通过自带的 **USB-C（PA11/PA12，CDC ACM 虚拟串口）**交互——**不需要 USB-TTL，
也不依赖 UART（PA9/PA10）**，所以某块板子 UART TX 坏了也能用。

同一份固件烧两块板子。在各自的 CDC 串口里输入命令选角色：一块当**发起方（init）**，
一块当**应答方（reply）**。发起方发帧，应答方原样回传，发起方校验**字节级往返**并打印
**PASS/FAIL** + FDCAN 诊断寄存器。

> CDC 配置直接照搬 `zephyr-usb-cdc-echo-1m` / `zephyr-can-bridge-slcan`（裸中断驱动 CDC ACM，
> 行式命令解析，不用 shell——因为板级 `cdc_acm_uart0` 没有 label，shell-chosen 不好接）。

## 为什么做这个

`zephyr-canfd-data-stress-psis100` 在和图莫斯 USB-CAN 通信时，**1M 仲裁/1M 数据**和
**500k 仲裁/5M 数据**两组速率不通。但那套测试把第三方 USB-CAN 放在一端，失败原因被搅在一起：
到底是 **XIAO 的 FDCAN 配置**，还是 **USB-CAN 适配器的时序**？

两块完全相同的 XIAO 对接，去掉了适配器这个变量：

- 两板也 **FAIL** → 是 XIAO 配置问题（时序覆盖、或 5M+BRS 缺 TDC）。FAIL 时自动 dump 寄存器，
  其中 **TDCR** 是关键线索。
- 两板 **PASS** → 是 USB-CAN 适配器时序不匹配。

这份固件沿用了 stress-psis100 的 **PSIS=100MHz** 时钟覆盖和**完全相同的位时序覆盖代码**
（1M 仲裁、1M/5M/8M 数据段分支原样搬过来），所以跑的就是失败的那条路径。

## 硬件接线

```
[120Ω]   XIAO A                       XIAO B   [120Ω]
        CANH (PB13) ──────────────── CANH (PB13)
        CANL (PB5)  ──────────────── CANL (PB5)
        GND        ──────────────── GND
```

- CANH 接 CANH，CANL 接 CANL，**不要接反**。
- 两板 **GND 共地**。
- 总线物理两端各一个 **120Ω** 终端电阻（只留两端，中间不要多放）。
- 线缆建议双绞；先短线（<30cm）跑通，再上长线。
- 板载收发器 STB（PB14）已由板级 DTS 的 `can_phy0` 托管，`can_start()` 自动唤醒，应用层不用管。
- **交互/供电**：两块板子各自的 USB-C 接电脑，会各枚举出一个 CDC COM 口。

## 编译烧录

```powershell
cd D:\workspace\platform-seeedboards\examples\seeed-xiao-stm32c5\zephyr-can-two-board
pio run -v
```

产物在 `.pio\build\seeed-xiao-stm32c5\`（`firmware.uf2` / `.hex` / `.elf`）。
**两块板子都烧同一份固件。**（UF2 烧法：双击 RESET 进 `XIAOC5BOOT` 卷，把 `firmware.uf2` 拷进去。）

## 打开 CDC 串口

- 设备管理器里找到两块板子各自的 CDC COM 口（Seeed VID 2886）。
- 用任意串口工具打开，**波特率随便填（如 115200）**——CDC 的波特率只是 USB line coding，
  不影响 USB-FS 的实际速率。
- ⚠️ **不要把波特率设成 1200**：固件带 UF2 助手，主机把 CDC line coding 设成 1200 会触发
  板子重启进 UF2 bootloader（这是正常的 UF2 烧录触发机制，和 `zephyr-usb-cdc-echo-1m` 一样）。

## 命令

在 CDC 串口里直接输入（小写，回车结束）。先验链路再查 bug：

```text
Board A (发起方):  init  500000 2000000 fd-brs
Board B (应答方):  reply 500000 2000000 fd-brs
```

发起方发完默认 1000 帧后，等 1s 收尾，自动打印结果：

```text
==== ROUND-TRIP RESULT ====
nominal=500000 data=2000000 fd-brs sent=1000 echoed=1000 loss=0
gap=0 content_err=0 tx_fail=0 state=active rxerr=0 txerr=0
can_stats bit=0 bit0=0 bit1=0 stuff=0 crc=0 form=0 ack=0 rx_overrun=0
==== PASS ====
```

应答方会一直回传，直到输入 `stop`。

### 命令一览

| 命令 | 说明 |
| --- | --- |
| `init <nominal> <data> <can\|fd\|fd-brs> [count] [fps]` | 发起方：配置+启动 CAN，发 count 帧（默认 1000，fps=0 满速），打印 PASS/FAIL |
| `reply <nominal> <data> <can\|fd\|fd-brs>` | 应答方：配置+启动 CAN，原样回传直到 stop |
| `stop` | 停止当前角色，移除滤波器，停 CAN |
| `status` | 打印当前计数（发起方看 sent/echoed/loss；应答方看 rx/echoed/dropped） |
| `id [init] [echo]` | 查/设两个 CAN ID（hex，默认 504 / 505，两者不能相同） |
| `clock` | 打印 CAN 内核时钟（本固件期望 100000000 Hz） |
| `regs` | 打印 FDCAN2 + RCC 关键寄存器（含 NBTP/DBTP/CCCR/PSR/ECR/**TDCR**） |
| `help` | 命令帮助 |

`fmt` 两块板必须一致：`can`（经典 CAN，8 字节）、`fd`（FD 不切速）、`fd-brs`（FD 数据段切高速）。

## 协议细节

- 发起方在 ID `0x504` 发，应答方在 ID `0x505` 回传；方向用不同 ID 隔离，**不受 CAN 自收发影响**。
- payload：`[magic 4B][seq 4B][timestamp 4B][pattern …]`，和 stress 固件完全一致。
- 应答方**原样回传**收到的帧（保留 FDF/BRS/DLC/data），所以 fd-brs 的数据段往返两个方向都被测到。
- PASS 条件：`loss==0`（echoed==sent）且 `content_err==0` 且未进 bus-off/stopped。

## 查 bug：跑这几组

先跑**对照组**（已知能通）确认接线/收发器/协议没问题：

```text
init  500000 2000000 fd-brs      (A)
reply 500000 2000000 fd-brs      (B)   -> 期望 PASS
```

再跑**两个失败速率**（两边参数必须一样）：

```text
# 失败组 1：1M 仲裁 / 1M 数据
init  1000000 1000000 fd-brs     (A)
reply 1000000 1000000 fd-brs     (B)

# 失败组 2：500k 仲裁 / 5M 数据
init  500000 5000000 fd-brs      (A)
reply 500000 5000000 fd-brs      (B)
```

再加一组经典 CAN 基线，把**仲裁段**和**数据段**问题分开：

```text
init  1000000 0 can              (A)   # 纯 1M 经典 CAN
reply 1000000 0 can              (B)
```

> 换速率前先 `stop` 两块板子，再各自 `init`/`reply` 新参数。

## 结果怎么读

- **PASS**：两板在该速率双向通信正常 → 原来的不通是 **USB-CAN 适配器**时序不匹配。
- **FAIL**：两板也不通 → 是 **XIAO 配置**问题。看自动 dump：
  - `TDCR=0000` 且在 5M+BRS 失败 → **收发器延迟补偿（TDC）没开**，这是 5M+BRS 失败的头号嫌疑。
    FDCAN 在数据段 >~2.5Mbps 时必须开 TDC，否则采样点被环路延迟推偏。
  - `PSR lec/dlec`：最后一次协议错误类型（ack=3 没有 ACK、bit0=5/bit1=4 电平、crc=6、stuff=1、form=2）。
  - `ECR tec/rec`：发送/接收错误计数；`tec` 飙到 255+ 会 bus-off。
  - `CCCR brse/fdoe`、`DBTP`、`NBTP`：确认 FD 模式和时序真的写进去了。
  - `CCIPR1 FDCANSEL`：应为 `1`（PSIS）；`can_core_clock` 应为 `100000000`。

## 多板 / 多 ID

默认一对板用 504/505。多块板同时挂总线时，给每对用不同 ID，例如 `id 506 507`。
ID 按十六进制解析：`504`、`0x504` 都行，范围 `0x000..0x7ff`，init 和 echo 不能相同。
