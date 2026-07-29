# XIAO STM32C5 CAN FD 100m Throughput Test Guide

本固件用于测试 XIAO STM32C5 在 100m CAN 线缆下的 CAN FD 发送、接收、双向/并发速率，并通过串口统计吞吐量。

## 上位机设置

USB-CAN/分析仪需要和固件命令保持一致：

| 项目 | 设置 |
| --- | --- |
| 模式 | CAN FD |
| CAN FD 格式 | ISO CAN FD |
| BRS | 开启 |
| 仲裁段速率 | 例如 `1000000`，即 1 Mbps |
| 数据段速率 | 例如 `8000000`，即 8 Mbps |
| 发送帧 ID | 标准帧 ID `00000504`，不要使用默认示例里的 `00000009` |
| 终端电阻 | 线缆两端各 120 ohm |
| 工作模式 | Normal/Active，不能 Silent |

说明：固件在数据段 `8000000` 时会手动把 XIAO data phase 采样点调到接近 80%，用于匹配部分 USB-CAN 工具的 8 Mbps 默认时序。启动命令后串口会打印实际 `brp/seg1/seg2/sjw/sample_point`。

## 命令格式

```text
cfd start <tx|rx|bidi|loop> [nominal] [data] [bytes] [seconds] [fps] [can|fd|fd-brs] [pattern]
```

常用参数：

| 参数 | 含义 |
| --- | --- |
| `tx` | XIAO 发送，上位机接收 |
| `rx` | XIAO 接收，上位机发送 |
| `bidi` | XIAO 发送，同时接收上位机发送 |
| `nominal` | 仲裁段速率，例如 `1000000` |
| `data` | 数据段速率，例如 `8000000` |
| `bytes` | 固定帧 payload 长度，最大 64 |
| `seconds` | 测试时间 |
| `fps` | 目标发送帧率，`0` 表示尽可能满速 |
| `fd-brs` | CAN FD + BRS，高速数据段测试使用这个 |

## 发送 ID 设置

固件默认发送标准帧 ID 为 `0x504`。多块 XIAO 同时发送时，必须给每块板设置不同发送 ID，避免同 ID 不同数据导致位冲突。

查询当前发送 ID：

```text
cfd id
```

设置发送 ID：

```text
cfd id 504
cfd id 505
```

说明：`cfd id` 参数按十六进制解析，支持 `504`、`0x504`、`00000504` 这类写法；当前只配置标准帧 ID，范围 `0x000..0x7ff`。建议在 `cfd start ...` 前设置。

## 发送测试

XIAO 发送，上位机接收并确认能正常打印数据段：

```text
cfd start tx 1000000 8000000 64 30 0 fd-brs
```

降低负载时可以指定帧率：

```text
cfd start tx 1000000 8000000 64 30 1000 fd-brs
```

1M/8M 长短帧发送命令：

```text
cfd start tx 1000000 8000000 8 30 0 fd-brs fixed-8
cfd start tx 1000000 8000000 64 30 0 fd-brs fixed-64
cfd start tx 1000000 8000000 64 30 0 fd-brs alt-8-64
cfd start tx 1000000 8000000 64 30 0 fd-brs mix-canfd
```

## 接收测试

上位机周期发送 CAN FD+BRS 帧，XIAO 只接收：

```text
cfd start rx 1000000 8000000 64 30 0 fd-brs
```

上位机发送列表中的帧配置建议：

| 项目 | 设置 |
| --- | --- |
| 帧类型 | 标准帧 |
| CAN类型 | CANFD加速 |
| 帧格式 | 数据帧 |
| ID(Hex) | `00000504`，如果当前是 `00000009`，需要改成 `00000504` |
| 数据长度 | `64`，短帧测试可用 `8` |
| 数据 | 至少以 `04 D5 5F 0C 00 00 00 00` 开头 |

接收端不需要特殊配置长短帧，固件会按实际收到的 DLC 统计长度分布。

1M/8M 长短帧接收时，XIAO 使用同一个命令：

```text
cfd start rx 1000000 8000000 64 30 0 fd-brs
```

上位机分别发送固定 8 字节、固定 64 字节、8/64 交替，或 8/12/16/20/24/32/48/64 循环帧。测试结束后看 `rx_len_hist` 确认长度分布。

## 双向测试

先让上位机开始周期发送 CAN FD+BRS 帧，然后 XIAO 输入：

```text
cfd start bidi 1000000 8000000 64 30 0 fd-brs
```

说明：

| 场景 | 含义 |
| --- | --- |
| 双向 | 两边同时有收发，重点验证功能正确 |
| 并发 | 两边同时高负载收发，重点验证极限吞吐和稳定性 |

实际命令都用 `bidi`，区别在于上位机发送频率。先低频验证双向，再逐步提高上位机发送频率做并发压力测试。

1M/8M 长短帧双向命令：

```text
cfd start bidi 1000000 8000000 8 30 0 fd-brs fixed-8
cfd start bidi 1000000 8000000 64 30 0 fd-brs fixed-64
cfd start bidi 1000000 8000000 64 30 0 fd-brs alt-8-64
cfd start bidi 1000000 8000000 64 30 0 fd-brs mix-canfd
```

若满压双向错误较多，先限制 XIAO 发送帧率验证稳定性：

```text
cfd start bidi 1000000 8000000 64 30 1000 fd-brs fixed-64
```

## 多节点并发测试

推荐接线：

```text
[120R] XIAO A ---- USB-CAN ---- XIAO B [120R]
```

连接要求：

| 项目 | 要求 |
| --- | --- |
| CANH | XIAO A、USB-CAN、XIAO B 的 CANH 全部接在一起 |
| CANL | XIAO A、USB-CAN、XIAO B 的 CANL 全部接在一起 |
| GND | 三个设备 GND 共地 |
| 终端电阻 | 只保留总线物理两端的 120 ohm |
| USB-CAN 终端 | USB-CAN 在中间时关闭终端电阻 |

两块 XIAO 同时发送、USB-CAN 接收监控时，先分别设置不同发送 ID：

```text
XIAO A:
cfd id 504
cfd start tx 1000000 8000000 64 30 0 fd-brs fixed-64

XIAO B:
cfd id 505
cfd start tx 1000000 8000000 64 30 0 fd-brs fixed-64
```

长短帧并发可把 `fixed-64` 换成 `fixed-8`、`alt-8-64` 或 `mix-canfd`。如果满压错误较多，先限制发送帧率：

```text
cfd start tx 1000000 8000000 64 30 1000 fd-brs fixed-64
```

USB-CAN 作为监控端时只接收即可；如果 USB-CAN 也参与发送，需要使用第三个不同 ID，例如 `0x506`。

## 长短帧发送

最后一个参数 `pattern` 控制 XIAO 发送的 payload 长度模式：

| 模式 | 含义 | 命令示例 |
| --- | --- | --- |
| `fixed-8` | 全 8 字节短帧 | `cfd start tx 1000000 8000000 8 30 0 fd-brs fixed-8` |
| `fixed-64` | 全 64 字节长帧 | `cfd start tx 1000000 8000000 64 30 0 fd-brs fixed-64` |
| `alt-8-64` | 8/64 字节交替 | `cfd start tx 1000000 8000000 64 30 0 fd-brs alt-8-64` |
| `mix-canfd` | 8/12/16/20/24/32/48/64 循环 | `cfd start tx 1000000 8000000 64 30 0 fd-brs mix-canfd` |

长短帧接收不用特殊命令，使用 `rx` 或 `bidi` 即可。

## 结果解读

测试结束或输入 `cfd stop` 后，会打印 `summary`、`perf`、`quality`、`estimate` 和长度分布。

### summary

```text
summary ... tx_ok=... tx_fail=... tx_cb_err=... rx=... checked=... gap=...
```

| 字段 | 含义 |
| --- | --- |
| `tx_ok` | 成功发送帧数 |
| `tx_fail` | 发送入队失败 |
| `tx_cb_err` | 已发送但回调报错 |
| `rx` | 接收总帧数 |
| `checked` | payload 格式正确且可检查序号的帧数 |
| `gap` | 接收序号缺口，用于估算丢包 |
| `content_err` | payload 内容校验错误 |
| `state` | CAN 控制器状态，正常应保持 `active` |
| `ack/bit/crc/form/stuff` | CAN 底层错误统计，正常测试应不持续增长 |

### perf

```text
perf elapsed_ms=30000 tx_fps=... rx_fps=... tx_payload_bps=... rx_payload_bps=... total_payload_bps=...
```

| 字段 | 含义 |
| --- | --- |
| `tx_fps` | XIAO 成功发送帧率 |
| `rx_fps` | XIAO 接收帧率 |
| `tx_payload_bps` | XIAO 发送 payload 吞吐，单位 bit/s |
| `rx_payload_bps` | XIAO 接收 payload 吞吐，单位 bit/s |
| `total_payload_bps` | 发送 + 接收总 payload 吞吐 |

吞吐量以 `total_payload_bps` 或对应方向的 `*_payload_bps` 为准。

### quality

```text
quality tx_error_permille=... rx_loss_permille=... total_error_permille=...
```

这些值单位是千分比，换算为百分比：

```text
百分比 = permille / 10
```

| 字段 | 含义 |
| --- | --- |
| `tx_error_permille` | 发送帧级错误率 |
| `rx_loss_permille` | 接收丢包率，根据 sequence gap 估算 |
| `total_error_permille` | 发送错误 + 接收丢包/内容错误的综合帧级错误率 |

例如：

```text
tx_error_permille=25
```

表示发送错误率约 `2.5%`。

### estimate

```text
estimate configured_nominal_bps=1000000 configured_data_bps=8000000 est_nominal_phase_bps=... est_data_phase_bps=...
```

| 字段 | 含义 |
| --- | --- |
| `configured_nominal_bps` | 配置的仲裁段速率 |
| `configured_data_bps` | 配置的数据段速率 |
| `est_nominal_phase_bps` | 估算仲裁段占用速率 |
| `est_data_phase_bps` | 估算数据段占用速率 |
| `est_total_bus_bps_no_stuff` | 不含 bit stuffing/错误重发的估算总线占用 |

注意：`estimate` 是按 CAN FD 帧格式估算，不包含 bit stuffing、错误帧、重发和仲裁等待；真实性能判断以 `perf` 和 `quality` 为准。

### 长度分布

```text
tx_len_hist 8:1000 64:1000
rx_len_hist 8:980 64:980
```

表示不同 payload 长度的帧数。用于确认长短帧模式是否按预期运行。

## 通过标准建议

一次测试可认为稳定通过时，建议同时满足：

```text
state 始终 active
tx_error_permille = 0
rx_loss_permille = 0
content_err = 0
ack/bit/crc/form/stuff 不持续增长
rx_overrun = 0
上位机能持续正常打印接收到的数据段
```

若出现 `warning/passive/bus-off`，或 `ack/bit/crc/form/stuff` 快速增长，说明当前线长、速率、负载或终端条件下不稳定。
