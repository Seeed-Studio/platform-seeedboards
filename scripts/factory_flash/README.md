# XIAO nRF54LM20B 出厂烧录支持包

## 概述

本目录包含通过 SWD/JLink 烧录 XIAO nRF54LM20B 的脚本。脚本自动搜索 nrfutil、JLink 和 objcopy，**不写死路径**，拷到任何环境都能用。

## 前置条件

- **nrfutil**: 安装 nRF Util（[下载](https://www.nordicsemi.com/Products/Development-tools/nRF-Util)，或把 `nrfutil.exe` 放到本目录）
- **JLink 调试器**: 通过 SWD 连接板子
- **PlatformIO GCC ARM 工具链**: 用于 bin→hex 转换（objcopy），安装 PIO 后自动存在

## 准备固件

运行脚本前，把固件文件拷到 `firmware/` 子目录：

```
factory_flash/
├── factory_provision.ps1
├── factory_flash.ps1
├── firmware/
│   ├── USB_DFU.hex        ← 合并固件（mcuboot + loader + app）
│   ├── keyfile.json       ← KMU 公钥
│   └── app.signed.bin     ← PIO 编译的签名 app
└── README.md（本文件）
```

- **USB_DFU.hex**: 来自 NCS 构建（mcuboot + loader + app 的合并固件）
- **keyfile.json**: KMU 公钥文件（root-ed25519）
- **app.signed.bin**: `pio run -e seeed-xiao-nrf54lm20b` 编出的签名 app（可选，也可运行时用 `-AppBin` 指定）

## 脚本说明

### factory_provision.ps1 — 出厂三步供给

**用途**：给空板（或需重置的板）一次性完成全部出厂设置。

**三步流程**：

| 步骤 | 操作 | 擦除模式 | 说明 |
|------|------|----------|------|
| 1 | 刷合并固件 | ERASE_ALL | 全擦 → 写 mcuboot + loader + app |
| 2 | 供 KMU 密钥 | — | 写 root-ed25519 公钥到 OTP |
| 3 | 刷 PIO app | ERASE_NONE | 只写 slot0，保留 mcuboot/loader/KMU |

**使用方式**：

```powershell
cd D:\...\scripts\factory_flash

# 方式一：自动检测 JLink，用 firmware/ 下的默认固件
.\factory_provision.ps1

# 方式二：指定 JLink 序列号
.\factory_provision.ps1 -SerialNumber 000069660778

# 方式三：指定固件路径（覆盖默认）
.\factory_provision.ps1 -MergedHex "C:\my\USB_DFU.hex" -KmuKey "C:\my\keyfile.json" -AppBin "C:\my\app.signed.bin"

# 方式四：指定 slot0 地址（28KB mcuboot 用 0x7000）
.\factory_provision.ps1 -Slot0Address 0x7000
```

**参数一览**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-SerialNumber` | 自动检测 | JLink 序列号 |
| `-MergedHex` | `firmware/USB_DFU.hex` | 合并固件路径 |
| `-KmuKey` | `firmware/keyfile.json` | KMU 密钥文件 |
| `-AppBin` | `firmware/app.signed.bin` | PIO 签名 app 路径 |
| `-Slot0Address` | `0x6000` | slot0 起始地址 |

**说明**：
- Step 2（KMU 供密钥）如果 `keyfile.json` 不存在会跳过（适用于板子已供过密钥的情况）
- Step 2 如果 `x-provision-keys` 返回非零会警告但不中断（板子可能已供过）
- 出厂后，板子可通过 USB DFU 更新，不再需要 JLink

---

### factory_flash.ps1 — 通用 SWD 烧录

**用途**：烧录任意单个固件（hex 或 bin），灵活用于开发调试。

**使用方式**：

```powershell
# 默认：烧 firmware/app.signed.bin 到 slot0（ERASE_NONE，保留 mcuboot）
.\factory_flash.ps1

# 指定固件（hex 直接烧，bin 自动转 hex 到指定地址）
.\factory_flash.ps1 -Firmware "C:\my\firmware.hex"
.\factory_flash.ps1 -Firmware "C:\my\app.signed.bin" -Address 0x6000

# 出厂全擦模式
.\factory_flash.ps1 -Firmware "C:\my\USB_DFU.hex" -EraseAll

# 指定 JLink
.\factory_flash.ps1 -SerialNumber 000069660778
```

**参数一览**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-Firmware` | `firmware/app.signed.bin` | 固件路径（.hex 或 .bin）|
| `-Address` | `0x6000` | .bin 文件的烧录偏移地址（slot0） |
| `-SerialNumber` | 自动检测 | JLink 序列号 |
| `-EraseAll` | 否 | 加此开关用 ERASE_ALL（全擦），否则 ERASE_NONE |
| `-Nrfutil` | 自动搜索 | nrfutil.exe 路径 |

**说明**：
- `.hex` 文件直接烧（地址内嵌）。`.bin` 文件自动转 hex 再烧。
- `-EraseAll` 会擦除整个芯片（包括 mcuboot），用于出厂或恢复。
- 不加 `-EraseAll` 只写目标区域，保留其他内容。

## 工具搜索机制

脚本**不写死路径**，自动搜索依赖：

**nrfutil.exe** — 按以下顺序搜索：
1. 脚本同目录
2. `C:\nrfutil\`
3. `%LOCALAPPDATA%\nrfutil\`
4. `%ProgramFiles%\Nordic Semiconductor\`
5. `%SystemDrive%\ncs\toolchains\`
6. 系统 PATH

**JLink 序列号** — 自动检测（`nrfutil device list` 找 12 位以上数字）。多个时让用户选。

**arm-none-eabi-objcopy**（bin→hex）— 搜索 `%USERPROFILE%\.platformio\packages\toolchain-gccarmnoneeabi*\bin\`
