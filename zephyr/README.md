# Zephyr framework 本地修复（patches & overrides）

本目录对 PlatformIO 的 `framework-zephyr` 包做本地修复，使 Seeed XIAO 系列板子
在当前 Zephyr 版本上可用。所有修复**集中登记**在 `fixes.yml`，由
`builder/frameworks/zephyr_fixes.py` 在构建前读取并应用到当前板对应的 framework 包。

## 目录结构

```
zephyr/
├── boards/          # 板级定义（zephyr/boards/arm/<board>/），不在本机制范围
├── patches/          # 补丁（unified diff）
│   └── <board>/      #   按板子分一层
│       └── 0001-*.patch
├── overrides/        # 覆盖（整文件）
│   └── <board>/      #   按板子分一层；其下相对路径 = framework 包内目标路径
│       └── drivers/...
├── fixes.yml         # 修复登记表（唯一真相源）
└── README.md         # 本文件
```

`<board>` = Zephyr board name（即 `zephyr/boards/arm/<同名>/` 的目录名，等于
`board.yml` 的 `board.name`），由 `platform.get_zephyr_board_name()` 解析。

## 选用哪种机制？

| 场景 | 机制 |
|---|---|
| 修改上游**已有**文件，且改动聚焦（几个 hunk） | `patch` |
| 上游文件**缺失**，或改动遍布全文件（整文件 backport 新 SoC 支持） | `override` |

- `patch`：unified diff，小而可审，幂等（已应用则跳过）。
- `override`：整文件覆盖目标路径；带可选 `baseline_sha` 防 framework 升级后 silent regression。

## fixes.yml 格式

见 `fixes.yml` 顶部注释。每个修复条目含 `id/type/path/target/applies_to`，可选
`upstream/baseline_sha/reason`。按 `boards[<board.name>]` 分节做**板/包隔离**，
`applies_to` 做**版本门控**。两级门控确保某板的修复绝不影响其他板的 framework 包，
升级 Zephyr 后旧条目自动失效、强制重新评估。

## 加新修复

1. 选机制：小改 → 在 `patches/<board>/` 放 `.patch`；整文件 → 在
   `overrides/<board>/<framework 内相对路径>/` 放文件（路径即 target）。
2. 在 `fixes.yml` 的 `boards[<board>]` 节（无则新建）加一条 `fixes` 条目，
   填 `path/target/applies_to/reason`，override 建议填 `baseline_sha`。
3. **无需改任何 builder 代码**。

## 加新板子

1. `platform.py` 的 `ZEPHYR_PACKAGE_BY_BOARD` 与 `ZEPHYR_BOARD_NAME_BY_BOARD` 各加一行。
2. 新建 `zephyr/patches/<board.name>/` 与 `zephyr/overrides/<board.name>/`（有修复才建）。
3. `fixes.yml` 加 `boards[<board.name>]` 节。

## 适配新 Zephyr 版本（升级 framework 包）

升级后 `applies_to` 不含新版本的条目会自动跳过（版本门控）。逐条评估：
- patch 已上游化 → 删该条；
- 仍适用 → `applies_to` 加新版本值；
- 需重做 → 新增条目指向新文件。
override 需重新算 `baseline_sha`（上游目标文件已变）。

## baseline_sha（override 防回归）

override 是整文件覆盖，framework 包升级后可能把新版静默盖掉。`baseline_sha` 记录
apply 时上游目标文件应有的 sha256；apply 前校验，不符则告警（不阻断构建）：

```bash
# 在 framework 包解压后算（首次构建后 framework 包已下载）
sha256sum <framework_dir>/<target>
```

填入对应 fix 的 `baseline_sha` 字段。可选；不填则只覆盖不校验。

## 模块划分

- `builder/frameworks/zephyr_fixes.py` — 调度：读 `fixes.yml` + 板/版本门控 + 分发
- `builder/frameworks/zephyr_patch.py`   — 执行器 A：把一个 `.patch` 应用到 framework 包（幂等）
- `builder/frameworks/zephyr_override.py` — 执行器 B：把一个 override 覆盖到 framework 包（含 baseline 校验）

执行器为无状态纯函数，只认「源文件 + framework 根 + 目标路径」，不读清单、不认识
板/版本，可独立单测。
