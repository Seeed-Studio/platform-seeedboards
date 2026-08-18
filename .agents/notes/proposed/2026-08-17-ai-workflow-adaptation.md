# AI 工作流适配方案

Status: proposed

## Context

`platform-seeedboards` 是 PlatformIO 平台包：其核心风险是 board metadata、包选择、构建适配、Zephyr 外部依赖、缓存状态、上传行为和硬件验证之间的集成一致性。它不同于 DeepSeek Harness 的 TypeScript plugin monorepo，不能直接复制后者的 package 规则、双语文档、每文件覆盖率或模型 transcript 快照。

当前根 `AGENTS.md` 已将仓库边界与开发流程分开：根规则说明适用范围、职责、兼容性和 notes；`platformio-development` skill 承担需要 fork 的实际改动与验证步骤。本方案定义下一步如何逐步补齐局部规则、skills、notes 生命周期和自动化验证。

## Proposal

### 1. 建立有限的 `AGENTS.md` 分层

根 `AGENTS.md` 保持为全仓库入口：仓库真源、受保护的用户契约、任务入口、证据要求和 Development Notes 导航。它不重复 fork、cache、build 或 PR 的操作步骤。

第一批候选子目录如下。每份子目录规则只写该目录特有、反复被遗漏且后果明显的约束；根规则必须在相关任务中要求读取它们，因为从仓库根目录启动 Codex 时不会自动预读全部嵌套 `AGENTS.md`。

| 目录 | 需要保护的事实 | 首批规则方向 |
| --- | --- | --- |
| `boards/` | board ID、framework list、upload/debug/内存声明是公开 PlatformIO 接口 | board manifest 只放 PlatformIO board 能力；不得用临时 builder 逻辑掩盖 manifest 缺失。 |
| `platform_cfg/` | 家族默认包与调试配置 | 只表达家族共性；板级差异应有显式 profile 或 board 来源。 |
| `builder/` | framework 入口与家族构建/产物/上传适配 | 保持 framework 与 family 责任分离；禁止仅凭 board 名称字符串扩散特例。 |
| `zephyr/` | local board、module、fix、patch、override 与 framework version 的对应关系 | 每项兼容修复说明适用版本和退出条件；禁止把 package cache 当作真源。 |
| `examples/` | 用户可复制的示例和稳定文档路径 | example 是回归契约，不只为 CI；变更需保留或明确迁移稳定路径。 |
| `scripts/ci/` | example 发现、构建选择、日志和固件产物 | 发现规则按声明的 framework/board 选择，不依赖脆弱目录命名。 |

暂不为每个 `builder/board_build/<family>` 或 `.github/` 建立规则。只有当父级规则无法清楚覆盖、且维护者反复需要同一局部知识时才继续细分。每份初版目标不超过约 20 条短规则，并应给出安全路径而不是笼统禁止。

### 2. 保留少量项目专用 skills

继续保留 `platformio-development`，它是有副作用的实现任务流程。新增 skill 应复用其步骤，而不是复制其全文。

| Skill | 触发条件 | 专属职责 | 不承担的职责 |
| --- | --- | --- |
| `platformio-pr-review` | 审查 PR、评估 diff、分析 CI 风险 | 按真实 base 审查完整 diff；追踪 board → package/profile → builder/framework → example/CI 的调用链；按路径、影响、证据输出问题 | 不要求 fork 输入；不创建提交、PR 或 cache 修改。 |
| `platformio-add-board` | 新增或正式支持一块板 | 收集 board ID、framework、MCU/上传/bootloader、家族归属、代表 example 和硬件证据；检查每层是否需要改动；随后调用 `platformio-development` 完成 fork 验证 | 不自行发明 package、Zephyr patch 或上传策略。 |

后续只有在 Zephyr package/cache/fixes 的改动已形成稳定、独立且重复的流程后，才添加 `platformio-zephyr-integration`。Skill 的 frontmatter 只描述用户目标和触发条件；正文写可操作步骤和最终输出。项目内 skill 是否自动发现取决于 Codex/插件配置，因此根规则应保留明确路径引用。

### 3. 采用四层 Development Notes 生命周期

采用 `.agents/notes/{proposed,implemented,rejected,archived}/`，规则以 `.agents/notes/README.md` 为准。初期不采用 DeepSeek 的分类子目录、双语文件、hash sidecar、归档 manifest 或“每个非平凡改动必须写 note”的强制门槛。

应写 note 的典型事项：board/profile 的唯一真源、Zephyr framework package 复用、cache/workspace 写入边界、patch/override 退出策略、上传兼容性、CI 覆盖策略。局部 bug 修复或机械格式调整不需要 note。

该机制不是任务管理：`proposed` 可以包含 plan；`implemented` 只描述当前已交付事实；`rejected` 保留关键否决理由；`archived` 是冻结历史。Agent 在设计跨层修改前搜索相关 active notes，而不是在每次会话读取整个目录。

### 4. 将稳定规则自动化

稳定规则是长期有效、可由机器明确判定、并能从仓库真源取得证据的不变式。自动化的目标是把“每位 reviewer 和 agent 都必须记住的检查”转为可重复失败的本地命令和 CI job；它不能取代对架构归属、硬件正确性或需求取舍的人工判断。

采用以下路径，而不是先写大而全的 lint：

1. 在 note 或目录规则中准确写出一个不变式，并指出唯一真源。
2. 收集一个应该通过的真实样本和一个应该失败的反例，确认规则不会误伤当前支持的变体。
3. 在 `scripts/ci/verify_<topic>.py` 实现一个快速、无网络、无 package-cache 依赖的检查；为复杂规则添加对应的单元测试或 fixture。
4. 先让开发者可单独运行该命令；稳定后加入最小的 GitHub Actions 检查或现有相关构建 workflow。
5. 在 `AGENTS.md` 或 owning skill 中引用该命令，但不要把已经稳定通过的机械检查反复作为人工 review finding。

第一批候选必须先通过现有仓库数据验证，再决定是否实现：

| 候选不变式 | 真源 | 预期检查 |
| --- | --- | --- |
| board manifest 可解析且 framework 声明有效 | `boards/*.json`、`platform.json` | JSON 完整性、每个 framework 名称存在。 |
| example 的 board/framework 组合有效 | `examples/**/platformio.ini`、boards | example 引用存在的 board，所选 framework 被该 board 声明支持。 |
| Zephyr 映射没有悬空引用 | `platform.py`、`platform.json`、`zephyr/` | board/package/Zephyr board/fix 路径相互存在且名称一致。 |
| CI 不遗漏受支持 example | `scripts/ci/` 与 tracked examples | 每个受支持项目被至少一个发现器选中，或有明确排除理由。 |

不应在第一批自动化的规则包括“实现是否优雅”“某项属性应该属于 board 还是 builder”“硬件行为正确”“不允许任何 board-name 判断”。这些需要通过设计 note、子目录规则、PR review 和真实构建/硬件证据判断。

### 5. 分阶段实施

1. **审查本方案。** 确认首批目录、skills、note 触发条件和候选不变式；不新增实现性 gate。
2. **建立导航。** 新增被确认的子目录 `AGENTS.md`，并更新根规则的显式导航；用一个真实任务检查规则是否过宽或遗漏。
3. **建立 workflows。** 创建并验证 `platformio-pr-review` 与 `platformio-add-board`；每个 skill 用真实或历史任务做一次前向测试。
4. **验证 notes 生命周期。** 用本方案和下一项跨层决策演练 `proposed → implemented/rejected`；在产生足够历史前不添加分类、双语或 archive 自动化。
5. **交付首个 gate。** 只选择一个已验证的候选不变式，提供通过/失败样本后接入 CI；根据误报和维护成本决定是否继续。

## Alternatives considered

### 直接复制 DeepSeek Harness 的完整机制

不采用。DeepSeek 的 package 层级、plugin seam、双语配对、严格文档预算、100% 覆盖率和模型快照服务于其大型 TypeScript agent 产品。PlatformIO 的主要风险是外部 toolchain、cache、board contract 和硬件，复制会增加维护负担而无法提高关键验证质量。

### 只保留根 `AGENTS.md`

不采用。根规则无法在不变得过长的情况下说明 Zephyr、board manifest、example 和 CI 的不同风险；未来 agent 也难以在相关目录获得局部约束。

### 对每个目录立即创建 `AGENTS.md`

不采用。过早细分会制造重复和空泛规则。首批只覆盖具有清楚边界和高集成风险的目录，其余等真实维护需求出现后再添加。

### 将所有检查都做成 CI lint

不采用。只有确定、稳定且能构造反例的规则才适合 gate；架构取舍、业务优先级和硬件行为仍需要 review、notes 和实机证据。

## Consequences

本方案会使 agent 的工作方式从“根提示词包含所有要求”转为“根规则导航到局部规则和 task skill”。代价是需要维护少量入口文件和在设计前搜索 notes；收益是局部知识不再挤占全局上下文，fork/缓存等高风险流程不会误用于只读任务，长期决策也能被后续工作找到。

首个自动化 gate 的实现需要先确认现有 manifest、example 和 Zephyr 映射的真实边界。未完成这一步前，任何检查只能是猜测，不能作为 CI 阻断条件。

## Validation

本 proposal 通过以下审查后才能进入实施：

1. 确认首批子目录是否覆盖实际高风险边界，且没有把临时实现细节写成永久规则。
2. 确认两项新增 skill 的触发条件与输出不重叠，并能在现有 Codex 使用方式中被明确引用。
3. 从候选稳定规则中选择一个，先证明真源、正例和反例，再批准实现。
4. 使用一次真实 board 或 Zephyr 改动验证：agent 能定位根规则、目标目录规则、相关 note 和正确 skill，而无需阅读无关文件。

## Related files

- [`AGENTS.md`](../../../AGENTS.md)
- [`platformio-development`](../../skills/platformio-development/SKILL.md)
- [`Development Notes`](../README.md)
- [`PlatformIO refactoring study`](../../../docs/REFACTORING_PIO.md)
