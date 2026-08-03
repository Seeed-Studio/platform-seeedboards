# XIAO nRF54LM20B — PIO 开发环境信息

> 完整环境清单,可传递给其他 agent / 新开发者。
> 最后更新:2026-08-03

## 核心路径

| 角色 | 路径 |
|---|---|
| **Platform 仓库** (cumin777 fork) | `D:/workspace/xiao_nrf54lm20b/platform-seeedboards` |
| Platform 分支 | `xiao_nrf54lm20b` |
| Platform 远端 | `https://github.com/cumin777/platform-seeedboards.git` |
| **Framework 包** (Zephyr 4.4.0, 有改动) | `C:/Users/seeed/.platformio/packages/framework-zephyr-nrf5440` |
| **PIO 缓存** (platform repo @src- 副本) | `~/.platformio/platforms/SeeedStudio/` 及 `SeeedStudio@src-*` |
| **NCS 构建目录** | `D:/workspace/build_usb_boot_dfu/` |
| **NCS 测试资料包** | `D:/workspace/xiao_nrf54lm20b_usb_dfu_test/` |
| **NCS 固件发布** | `D:/workspace/aaamemory/xiao/20b/firmware/release_xiao_nrf54lm20b_testplan/usb_dfu/` |

## Framework 包内的改动（不在 git repo, live 生效）

> 这些文件在 `C:/Users/seeed/.platformio/packages/framework-zephyr-nrf5440/` 下,直接编辑即生效,不需要 @src- 同步。

### 板子设备树 (`boards/seeed/xiao_nrf54lm20b/`)

**`nrf54lm20b_cpuapp_common.dtsi`:**
- 分区: OLD bootloader 布局
  - mcuboot: 24 KiB @0x0 (结束 0x6000)
  - slot0 (app): @0x6000 / 1784 KiB (0x1BE000)
  - slot1 (loader): @0x1c4000 / 116 KiB
  - storage: @0x1e1000 / 16 KiB
- `zephyr,boot-mode = &boot_mode0` (gpregret1 retention, 用于 1200 touch 后写入 boot-mode)
- `&gpregret1` 下有 `boot_mode0: boot_mode@0 { compatible = "zephyr,retention"; reg = <0x0 0x1>; };`
- `zephyr,console = &cdc_acm_uart` (USB CDC ACM console)
- `cdc_acm_uart` 节点在 `&usbhs` (DWC2 控制器) 下

**`Kconfig.defconfig`:**
```kconfig
config BOOTLOADER_MCUBUBOOT    default y
config RETENTION              default y
config RETENTION_BOOT_MODE   default y
config RETAINED_MEM          default y
config RETAINED_MEM_NRF_GPREGRET  default y
config UART_LINE_CTRL        default y
config REBOOT               default y
config CDC_ACM_SERIAL_VID    hex default 0x2886
config CDC_ACM_SERIAL_PID    hex default 0x8013
config CDC_ACM_SERIAL_PRODUCT_STRING  string default "XIAO_NRF54LM20B"
```

### 构建脚本 (`scripts/platformio/platformio-build.py`)

- **`GenerateMCUbootBinaryCmd()`**: 默认签名(去掉了 `mcuboot-image` opt-in 门;板子声明 imgtool 参数就自动签)
- **`--pure`**: 当 `board.get("build.zephyr.bootloader.pure")` = true 时传 `--pure`(mcuboot BOOT_SIGNATURE_TYPE_PURE 要求 TLV 0x25)
- **`get_boot_signature_key_file()`**: 默认 key → `root-ed25519.pem` + 相对 key 解析
- **ZEPHYR_MODULES**: 自动注册 `_pio/modules/xiao_dfu_reset` 进模块列表

### 1200bps DFU 触发模块 (`_pio/modules/xiao_dfu_reset/`)

**`src/xiao_dfu_reset.c`:**
- `SYS_INIT(APPLICATION)`: 遍历所有 USBD context → `usbd_msg_register_cb` 注册回调
- 回调 `xiao_dfu_msg_cb`: 检测 `USBD_MSG_CDC_ACM_LINE_CODING` (type=8) → `uart_line_ctrl_get(BAUD_RATE)` → 如果 baud=1200 → `bootmode_set(BOOT_MODE_TYPE_BOOTLOADER)` + `sys_reboot(SYS_REBOOT_COLD)`
- 调试 printk 通过 `k_work` 延迟到 system workqueue(避免在 USBD 回调中直接 printk 导致 USB 栈重入)
- **CONFIG_XIAO_DFU_RESET**: Kconfig `default y if BOARD_XIAO_NRF54LM20B_NRF54LM20B_CPUAPP`

**`Kconfig` / `CMakeLists.txt` / `zephyr/module.yml`:** 标准 Zephyr 模块结构

## Platform 仓库内的改动（在 git, 已提交到 cumin777）

> `D:/workspace/xiao_nrf54lm20b/platform-seeedboards/` 分支 `xiao_nrf54lm20b`

### 关键提交历史

| Commit | 内容 |
|---|---|
| `9ba53b6` | 上游 Seeed-Studio main 对齐(基线) |
| `0b93879` | α_test 板子目录微调(soc 改名 + 分区) |
| `f5bd6ea` | variant 修复 nrf54lm20b/cpuapp |
| `6e0e953` | USB DFU 机制(默认签名 + WaitForDfuPort + imgtool 参数) |
| `897a65e` | OLD bootloader 分区对齐(slot0 @0x6000) |
| `e50ecde` | USB CDC 默认开 + 20B CDC blink sample |
| `86df08c` | prj.conf 清理 |
| `fbd8996` | 自动 DFU(DfuUpload1200 + VID:PID 过滤 + auto-reset) |
| `bc544d5` | 出厂供给脚本(portable) |

### 文件清单

**`boards/seeed-xiao-nrf54lm20b.json`:**
```json
"build": {
    "zephyr": {
        "variant": "xiao_nrf54lm20b/nrf54lm20b/cpuapp",
        "bootloader": {
            "header_len": "0x800",
            "flash_alignment": "16",
            "slot_size": "0x1BE000",
            "app_version": "0.0.1",
            "signature_key_file": "root-ed25519.pem",
            "pure": "true"
        }
    }
},
"upload": {
    "protocol": "nrfutil-mcumgr",
    "use_1200bps_touch": true,
    "wait_for_upload_port": true
}
```

**`builder/board_build/nrf/nrf_build.py`:**
- `DfuUpload1200()`: 统一 DFU 口解析器(防砖)。按优先级解析:
  - 显式 `upload_port` → 按 VID:PID 判断是 loader 还是 app
  - loader CDC(2886:0013)已在 → 板子已在 DFU(手动 P0.09+复位 / 空槽 NO_APPLICATION)→ **直接用,跳过 1200 touch**(防砖快速路径)
  - app CDC(2886:8013)在 → touch 1200 → 轮询只认 loader CDC(2886:0013)
  - 都不在 → 提示"按住 P0.09+复位"并轮询等 loader CDC(60s)
- 常量:`_APP_CDC_VIDPID=2886:8013`、`_LOADER_CDC_VIDPIDS=("2886:0013",)`(元组,可加 legacy loader VID:PID)
- `RESETCMD`: `nrfutil mcu-manager serial reset` (upload 后自动复位)
- `--timeout 120`
- (旧 `WaitForDfuPort()` 已删,逻辑并入 `DfuUpload1200` 第 4 分支)

**`scripts/factory_flash/factory_provision.ps1`:** 出厂 3 步(合并固件 → KMU → PIO app),自包含搜索工具
**`scripts/factory_flash/factory_flash.ps1`:** 通用 SWD 烧录(单独固件)
**`scripts/factory_flash/README.md`:** 使用说明
**`docs/usb-dfu-plan.md`:** 完整 DFU 设计文档
**`examples/seeed-xiao-nrf54lm20b/zephyr-blink/`:** 20B CDC blink sample(blink + printk via USB CDC)

## 技术参数汇总

| 参数 | 值 |
|---|---|
| **USB VID:PID (app)** | `0x2886:0x8013` (framework Kconfig `CDC_ACM_SERIAL_PID`) |
| **USB VID:PID (DFU loader)** | `0x2886:0x0013` (loader usb_mcumgr,出厂 hex `scripts/factory_flash/firmware/USB_DFU.hex` 内 device descriptor @0x1D2BAD) |
| **USB 设备名** | `XIAO_NRF54LM20B` |
| **签名算法** | Ed25519 PURE (imgtool `--pure`, TLV 0x25) |
| **签名密钥** | `root-ed25519.pem` (公钥 d4b31ba4..., 在 KMU OTP) |
| **mcuboot 模式** | firmware-loader (`BOOT_FIRMWARE_LOADER` + `BOOT_FIRMWARE_LOADER_BOOT_MODE` + `_NO_APPLICATION`) |
| **分区布局** | mcuboot 24KB @0x0 / app slot0 @0x6000 1784KB / loader slot1 @0x1c4000 116KB / storage @0x1e1000 16KB |
| **DFU 触发** | 1200-bps touch (USBD_MSG_CDC_ACM_LINE_CODING → bootmode → sys_reboot) |
| **Framework 版本** | Zephyr 4.4.0 (PIO 包版本号 3.40400.260428) |
| **mcuboot revision** | `ee39e8d6` (upstream, 支持 BOOT_FIRMWARE_LOADER) |
| **Toolchain** | gccarmnoneeabi 1.80201.181220 (GCC 8.2.1) |

## 缓存注意（重要）

- **Platform repo** 改动(`nrf_build.py`、board json)PIO 读自 `~/.platformio/platforms/SeeedStudio*/`(@src- 副本缓存)。**改后必须同步**:
  ```bash
  for d in ~/.platformio/platforms/*/; do
    [ -f "$d/boards/seeed-xiao-nrf54lm20b.json" ] && cp <repo>/boards/seeed-xiao-nrf54lm20b.json "$d/boards/"
    [ -f "$d/builder/board_build/nrf/nrf_build.py" ] && cp <repo>/builder/board_build/nrf/nrf_build.py "$d/builder/board_build/nrf/"
  done
  ```
- **Framework 包** 改动(板子 dtsi/Kconfig、platformio-build.py、xiao_dfu_reset 模块)**live 生效**, 不需要同步。
- Sample app(prj.conf/CMakeLists)从 α_test 仓库 live 路径读。

## 完整工作流

### 出厂(空板 → 全部就绪)

```powershell
cd D:\workspace\xiao_nrf54lm20b\platform-seeedboards\scripts\factory_flash
# 先把 USB_DFU.hex + keyfile.json 拷到 firmware/ 子目录
.\factory_provision.ps1 -SerialNumber <JLink_S/N>
# → 合并固件(ERASE_ALL) → KMU 供密钥 → PIO app(ERASE_NONE)
```

### 日常更新(app 已在板)

```powershell
cd D:\workspace\xiao_nrf54lm20b\platform-seeedboards\examples\seeed-xiao-nrf54lm20b\zephyr-blink
pio run -t upload -e seeed-xiao-nrf54lm20b
# → DfuUpload1200: app CDC(2886:8013)在 → touch 1200 → 轮询认 loader CDC(2886:0013) → mcumgr 上传 → auto-reset
```

### 防砖恢复(app 崩溃 / 空 slot,无 app CDC)

不用 SWD,直接 PIO 恢复:

```powershell
pio run -t upload -e seeed-xiao-nrf54lm20b
# 此时板子无 app CDC(2886:8013)。按住 Button0 / P0.09 + 复位进 DFU(loader 跑起来,出 2886:0013)
# → DfuUpload1200: 检测到 loader CDC 已在 → 直接用、跳过 touch → mcumgr 上传好 app → reset 起来
# (若上传时还没按键,PIO 会提示并轮询等 2886:0013 出现,60s 超时)
```

### 工厂恢复/单独 SWD 烧录

```powershell
.\factory_flash.ps1 -Firmware <hex_or_bin> [-SerialNumber <S/N>] [-EraseAll]
```
