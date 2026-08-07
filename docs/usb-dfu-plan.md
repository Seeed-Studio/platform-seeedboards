# USB DFU(firmware-loader 三镜像)默认化 — XIAO nRF54LM20B

> 实施计划。分支 `xiao_nrf54lm20b`。配套 NCS 测试资料包:`D:/workspace/xiao_nrf54lm20b_usb_dfu_test/`。

## Context(为什么做这个)

用户目标:`pio run`(seeed-xiao-nrf54lm20b)→ 编译固件 → 等用户按 P0.09+复位进 DFU → 检测到 DFU 口 → mcumgr 烧录。USB DFU 要**默认给所有 PIO 编译的固件**配上。

**关键:这是 firmware-loader(三镜像)架构**(参考 NCS sample `cumin777/nrf54lm20a_test` 分支 `20b-test_plan` 的 `test_plan/usb-boot-dfu`),**不是** nRF 常见的"mcuboot 内置 USB 串行恢复"。固件共三段程序:
1. **mcuboot**(bootloader,@0x0)— firmware-loader 模式;触发时引导 loader 而非 app。
2. **loader 镜像**(usb_mcumgr,在 slot1)— 独立程序,暴露 USB CDC + mcumgr/imgmgr;**DFU 在这里执行,不在 mcuboot**。
3. **app**(slot0)— 用户固件,经 DFU 更新。

### 三个硬约束(已核实)
- **PIO 不跑 Zephyr post-build** → Zephyr 原生 imgtool 签名(`cmake/mcuboot.cmake` 的 `extra_post_build_commands`)在 PIO 下从不执行 → `zephyr.signed.bin` 不产生 → 这是 DFU 今天不通的**根因**。修复:让 PIO 自己的 imgtool 默认签名。
- **PIO 做不了 sysbuild**(`platformio-build.py:run_cmake` 只解析单 app codemodel;sysbuild 是多镜像元构建,改造深且险)。→ **mcuboot+loader 用 NCS 预编 hex 出厂烧一次**;**app 走 PIO 每次构建+签名**。
- **公钥必须嵌进 mcuboot**:没公钥 → mcuboot 验签不过 → 程序跑不起来(用户实测)。出厂 mcuboot 带公钥;app+loader 用对应私钥签名。

### 两条路径(回应"自由度"顾虑)
- **PIO 路径(本平台)**:mcuboot+loader 预编 hex(NCS 资料包,出厂烧一次)+ app 每次 `pio run` 签名。
- **NCS 路径(随平台提供 sample)**:把 firmware-loader DFU 的 sysbuild 配置(reference 的 `usb-boot-dfu`)作为 NCS sample 提供。NCS 用户 `west build --sysbuild` 出**完整合并固件(自带正确的 firmware-loader mcuboot)**,烧它=自洽,不会"冲掉 DFU"。
- 两条路径**共享板子配置**(mcuboot.conf firmware-loader 模式、分区、密钥)——保证 mcuboot(无论 NCS sysbuild 还是预编)用同一公钥验签 app(无论 NCS 还是 PIO 签)。

### PIO 的职责(关键澄清)
**PIO 不编译 mcuboot / loader**——它们出厂来自 NCS `06-USB-DFU.hex`。PIO 的活:**编译 + 签名用户自己的 app**(imgtool,Ed25519 PURE,root-ed25519.pem),让预编 mcuboot 能验签、引导、经 mcumgr 更新。所以"在 PIO 里加 mcuboot 支持" = **app 侧签名 + 上传流程**,不是 mcuboot 编译。没有签名 → PIO 编出的 app 未签名 → 预编 mcuboot 拒收(验签不过)→ 跑不起来。
**据此简化**:① mcuboot soc conf——不要(PIO 不编 mcuboot);② zephyr.py sysbuild——不要(PIO 不编 mcuboot/loader);③ 板子 mcuboot.conf 的 firmware-loader 改造(Phase 1)——属 NCS 路径(Phase 7)共享板子配置,PIO 不直接用。
**PIO 实际要改的只有三处**:a) `platformio-build.py` 默认 imgtool 签名(Ed25519 PURE + root-ed25519.pem);b) `nrf_build.py` 上传流程(WaitForDfuPort + nrfutil mcumgr);c) board json imgtool 参数。
**⚠️ sdk-nrf 已删除**(环境里没有);usb_mcumgr loader 仅存在于 NCS `06-USB-DFU.hex`(预编)。NCS 重建(Phase 7)需用户自己的 sdk-nrf。

### 可复用的现成基建(已核实)
- mcuboot 预打包在 framework `_pio/bootloader/mcuboot/`(rev `ee39e2d6`),是 Zephyr module,`IMGTOOL` 可被 CMake 找到;imgtool 支持 Ed25519/RSA。
- **sdk-nrf 已删除**;usb_mcumgr loader 仅在 NCS `06-USB-DFU.hex` 预编(PIO 不重建)。
- 板子(framework `boards/seeed/xiao_nrf54lm20b/`,**live 读取**)的 app 默认配置:USB CDC 全 resolve 到 y(UDC_DWC2 自动选;DWC2 控制器 `snps,dwc2`)。
- Flash 几何:`write-block-size=16`、`erase-block-size=4096`、`ROM_START_OFFSET=0x800`、slot0 `0x11000/0x70000`、slot1 `0xf1000/0x70000`。imgtool 参数:`--header-size 0x800 --align 16 --slot-size 0x70000`。
- `nrf_build.py` 已有 `nrfutil-mcumgr` 上传器(pip 装 nrfutil),`BeforeUpload` 里有 `WaitForNewSerialPort`/`list_serial_ports` 可复用。
- 板子 button0 = P0.09(`mcuboot-button0` alias)。

## 关键决策(已定)

- **D1 loader 镜像**:usb_mcumgr,但 **PIO 不自建**——预编在 NCS `06-USB-DFU.hex`(slot1)。sdk-nrf 已删,PIO 不能重建 loader(frozen);PIO 路径不依赖 sdk-nrf。NCS 重建(Phase 7)需用户 sdk-nrf。
- **D2 签名密钥**:**`root-ed25519.pem`(Ed25519 PURE)**——已确认。NCS mcuboot 构建用 `CONFIG_BOOT_SIGNATURE_KEY_FILE=root-ed25519.pem`+`BOOT_SIGNATURE_TYPE_ED25519=y`+`BOOT_SIGNATURE_TYPE_PURE=y`;其公钥(=`d4b31ba4…`)= keyfile.json 的 KMU/SB value,**逐字匹配**。它是 NCS mcuboot bundled **公开默认** Ed25519 key(非秘密)→ 对开发板合理(用户自由签、无丢失风险)。PIO imgtool 用它签 app 即对齐。
- **两层 key 澄清**:`BOOT_SIGNATURE_USING_KMU is not set` → mcuboot 验 app 用**嵌 mcuboot 的 Ed25519 公钥**(PURE,不靠 KMU);KMU(keyfile.json/provision_kmu.ps1)是更底层 **SB secure-boot 校验层**(出厂 JLink 供给,验 mcuboot 镜像)。两层共用 root-ed25519.pem。PIO 只用 root-ed25519.pem 签 app;KMU/SB 是出厂(用 NCS 资料包的 provision_kmu.ps1)。
- **D3 mcuboot+loader 供给**:出厂一次——用 NCS `06-USB-DFU.hex`(预编)+ `provision_kmu.ps1`。不随 app 每次重建。
- **D4 入口**:GPIO 按键 P0.09 + NO_APPLICATION(用户要"按键")。

## 实施阶段

### Phase 1 — 板子改 firmware-loader 模式(framework,live;同步到 platform repo 仅为一致)— 属 NCS 路径共享配置
- `framework-zephyr-nrf54lm20/boards/seeed/xiao_nrf54lm20b/mcuboot.conf`:
  - **删** 经典串行恢复:`CONFIG_MCUBOOT_SERIAL`、`CONFIG_BOOT_SERIAL_CDC_ACM`、`CONFIG_BOOT_SERIAL_WAIT_FOR_DFU*`、`CONFIG_BOOT_SERIAL_NO_APPLICATION`、`CONFIG_BOOT_SERIAL_ENTRANCE_GPIO`。
  - **加** firmware-loader:`CONFIG_BOOT_FIRMWARE_LOADER=y`、`CONFIG_BOOT_FIRMWARE_LOADER_ENTRANCE_GPIO=y`(P0.09)、`CONFIG_BOOT_FIRMWARE_LOADER_NO_APPLICATION=y`。
  - 签名(D2):改 **Ed25519 PURE** → `CONFIG_BOOT_SIGNATURE_TYPE_ED25519=y`+`CONFIG_BOOT_SIGNATURE_TYPE_PURE=y`+`CONFIG_BOOT_SIGNATURE_KEY_FILE=root-ed25519.pem`(对齐 NCS)。删 RSA-3072。
- 分区(`nrf54lm20b_cpuapp_common.dtsi`):保持 slot0=app / slot1=loader(loader ~116KB 放得进 slot1 448KB)。
- 镜像到 `platform-seeedboards/zephyr/boards/arm/xiao_nrf54lm20b/`(missing-only seed,保持同步)。

### Phase 2 — 让 PIO 默认 imgtool 签名(framework,live)— 核心使能
- `framework-zephyr-nrf54lm20/scripts/platformio/platformio-build.py`:
  - `GenerateMCUbootBinaryCmd()`(~1834):**去掉 `mcuboot-image` opt-in 门**;改为读 imgtool 参数,缺则优雅跳过、有则签名。让签名成为**板级默认**(由 board json 参数驱动),非 per-sample target。
  - `get_boot_signature_key_file()`(~521):默认 key → `root-ed25519.pem`(D2,Ed25519 PURE,对齐 NCS)。
  - imgtool 参数:header_size 0x800 / align 16 / slot_size 0x70000。

### Phase 3 — board json 声明 imgtool 参数(platform,需 @src- 同步)
- `boards/seeed-xiao-nrf54lm20b.json`:`build.zephyr.bootloader` = `{header_len:"0x800", flash_alignment:"16", slot_size:"0x70000"}`;`upload.protocol` 已是 `nrfutil-mcumgr`。

### Phase 4 — 出厂:用 NCS 资料包的合并固件(PIO 不自建 mcuboot/loader)
- 直接用 NCS 资料包 `D:/workspace/xiao_nrf54lm20b_usb_dfu_test/06-USB-DFU.hex`(NCS sysbuild 产物:mcuboot[SB/KMU 校验 + 嵌 root-ed25519 公钥 + firmware-loader 模式] + usb_mcumgr loader + app)。**PIO 不自建 mcuboot/loader**。
- 出厂烧:`06-USB-DFU.hex`(JLink 全量)+ `provision_kmu.ps1`(供 SB/KMU 公钥,keyfile.json)。把这两样 + keyfile.json + `run_usb_dfu.ps1` 随平台提供给用户(出厂/恢复用)。
- NCS 用户要自建:用提供的 `usb-boot-dfu` sysbuild sample(Phase 7)`west build --sysbuild` 出同样合并固件。

### Phase 5 — 上传流程:WaitForDfuPort(platform,需 @src- 同步)
- `nrf_build.py` 的 `nrfutil-mcumgr` 分支(~435):在 `UPLOADCMD` 前插 `WaitForDfuPort` 动作——快照 `list_serial_ports()`、提示"按住 P0.09 + 复位"、`env.WaitForNewSerialPort(before)` 等新 CDC 口(loader 的 CDC,因 mcuboot 按键后引导 loader)、设 `UPLOAD_PORT`。
- target_firm(~282):`env.MCUbootImage($BUILD_DIR/zephyr/zephyr.signed.bin, env.ElfToBin(...))`,失败优雅回退未签名。

### Phase 6 — 默认化 + 验证
- 确认:任何 seeed-xiao-nrf54lm20b 的 `pio run`(无 per-sample opt-in)都签名 app + 走 wait-for-DFU 上传。

### Phase 7 — 提供 NCS sysbuild sample(NCS 用户完整构建路径)
- 把 reference 的 `usb-boot-dfu`(sysbuild:mcuboot + usb_mcumgr loader + app;firmware-loader 模式;单槽;密钥配置)作为 NCS sample 随平台仓库提供(如 `examples/ncs-usb-boot-dfu/`,或文档指向 `cumin777/nrf54lm20a_test` 的 `20b-test_plan/test_plan/usb-boot-dfu`)。
- NCS 用户 `west build --sysbuild -b xiao_nrf54lm20b/nrf54lm20b/cpuapp` 出**自带正确 mcuboot 的合并固件**,烧录自洽。
- 与 PIO 路径**共享**板子 mcuboot.conf / 分区 / 密钥(Phase 1、D2)。

## @src- 同步注意
- **framework 包**改动(board dir、`platformio-build.py`、mcuboot、key)**live 生效**。
- **platform repo** 改动(`nrf_build.py`、board json、`platform.json`)PIO 读自 `~/.platformio/platforms/Seeed Studio@src-b83000bc.../`(已确认 stale);改后**必须同步**进该 @src- 副本(`for d in ~/.platformio/platforms/*/; do ... cp ...; done` 或重装 file:// 平台)。

## 验证(端到端)
- **V1 出签名 bin**(无硬件):`pio run -e seeed-xiao-nrf54lm20b` → 见 `Signing` + `zephyr/zephyr.signed.bin` 存在;imgtool getpub 报 Ed25519;header 0x800/align 16/slot 0x70000 对。
- **V2 mcuboot+loader 烧录**(探针一次):烧 NCS `06-USB-DFU.hex` + `provision_kmu.ps1`;空 slot0 复位 → mcuboot 自动引导 loader(NO_APPLICATION)→ 出现新 CDC 口。
- **V3 按键→DFU→mcumgr**(硬件):已有 app 时 `pio run -t upload` → 签名 → 提示按 P0.09+复位 → loader CDC 出现 → mcumgr 上传新 app 到 slot0 → 复位跑新 app。
- **V4 默认化**:换别的 sample(zephyr-gpio/ble)无额外 ini → 同样签名 + wait-for-DFU。
- **V5 砖机恢复**:擦 slot0 → 复位自动进 loader(NO_APPLICATION,免按键)→ 上传新 app → 起来。
- **V6 NCS 路径自洽**:用提供的 `usb-boot-dfu` sample `west build --sysbuild` 出合并固件 → 烧录 → DFU 仍可用;NCS 签的 app 与 PIO 签的 app 能被同一 mcuboot 验签(共享 root-ed25519.pem)。

## 关键文件
- `framework-zephyr-nrf54lm20/scripts/platformio/platformio-build.py` — `GenerateMCUbootBinaryCmd`(默认签名,P2)+ `get_boot_signature_key_file`(默认 key,P2)。**framework,live**。
- `framework-zephyr-nrf54lm20/boards/seeed/xiao_nrf54lm20b/mcuboot.conf` — 改 firmware-loader 模式(P1)。**framework,live**(+同步 platform repo)。
- `platform-seeedboards/builder/board_build/nrf/nrf_build.py` — `nrfutil-mcumgr` 签名 target_firm(P5)+ `WaitForDfuPort`(P5)。**platform,需 @src- 同步**。
- `platform-seeedboards/boards/seeed-xiao-nrf54lm20b.json` — imgtool 参数(P3)。**platform,需 @src- 同步**。
- NCS 资料包 `D:/workspace/xiao_nrf54lm20b_usb_dfu_test/`(`06-USB-DFU.hex` + `keyfile.json` + `provision_kmu.ps1` + `run_usb_dfu.ps1`)— 出厂/恢复用,随平台提供。

## 范围与风险
- PIO 侧改动集中在 3 处(platformio-build.py 签名默认 / nrf_build.py 上传流程 / board json 参数),不碰 mcuboot 编译。
- 签名默认化改的是 framework 包的 `platformio-build.py`(影响该 framework 下板子签名行为);若要仅限 lm20b,改为读 board json 的 signature_key_file。
- loader(usb_mcumgr)frozen 在 NCS 预编版本(不能重建,因 sdk-nrf 已删);要更新 loader 需恢复 sdk-nrf 走 NCS 重建。
