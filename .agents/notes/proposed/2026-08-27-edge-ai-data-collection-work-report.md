# Edge AI 数据采集方式替代工作报告

更新时间：2026-08-27

## 1. 开发背景

当前项目的目标是为 Seeed Studio XIAO nRF54LM20B 建立完整的手势识别流程：

```text
IMU 数据采集 → 数据集整理 → Edge AI Lab 训练 → Axon NPU 部署 → 板端识别
```

项目早期为了尽快验证 USB CDC 和板载 LSM6DS3TR-C IMU，开发了自定义 sample：

```text
examples/seeed-xiao-nrf54lm20b/edgeai-gesture-data-collection
```

该 sample 使用 USB CDC 命令控制固定时长录制，PC 端脚本负责自动发送命令、接收
CSV、按标签保存，并通过 `prepare_dataset.py` 合并为上传文件。

这套方案适合硬件 bring-up 和小规模 PoC，但与 Nordic 官方的数据采集、标注和数据
清洗流程不完全一致，用户需要维护自定义命令、录制时序、标签和数据转换逻辑。

## 2. 官方数据集获取方式

Nordic Edge AI Lab 当前提供的推荐工作流是：

```text
Data Collection Firmware / Data Forwarder
        ↓
Data Collection Desktop app
        ↓
Dataset Builder
        ↓
Edge AI Lab dataset upload
```

各部分职责如下：

- **Data Collection Firmware / Data Forwarder**：从开发板持续转发原始传感器数据。
- **Data Collection Desktop app**：接收和可视化数据，并对手势片段进行标注。
- **Dataset Builder**：将标注后的连续录音切分、清洗、整理成训练所需的数据集。
- **Edge AI Lab**：选择特征、目标列和 Session ID，执行训练、验证和模型导出。

相比当前 DIY 方案，官方流程更适合正式数据集，因为连续录音、标签、手势分段和
清洗都有明确的工具支持。

## 3. 替代决策

后续正式数据采集计划采用 Nordic 官方的 Data Forwarder + Data Collection Desktop
app + Dataset Builder 流程，逐步替代当前 DIY 采集方式。

当前 DIY sample 暂时保留，定位调整为：

- 验证 XIAO nRF54LM20B 的 IMU、USB CDC 和采样率配置；
- 在官方工具尚未完成 XIAO nRF54LM20B 适配前，快速生成少量 PoC 数据；
- 作为底层 CDC 数据通路的回归样例。

DIY sample 不再作为正式生产数据采集工具的长期目标。

## 4. 迁移时需要保持的接口

无论使用 DIY sample 还是官方工具，送入训练流程的数据都必须与板端推理保持一致：

| 项目 | 要求 |
|---|---|
| 传感器 | 3 轴加速度 + 3 轴陀螺仪 |
| 采样率 | 100 Hz |
| 特征顺序 | `acc_x`, `acc_y`, `acc_z`, `gyro_x`, `gyro_y`, `gyro_z` |
| 目标列 | 数字 `class`，从 `0` 开始连续编号 |
| Session ID | 每次独立连续录音使用不同的数字 ID，并在平台中选择为 Session ID |
| 数据值 | 所有特征和辅助列都必须是数值，不能包含字符串或空值 |

官方流程还要求对非连续手势进行分段，使手势峰值位于窗口中间，并删除录音开头、
结尾和错误操作产生的无效数据。

## 5. 当前 DIY 方案与官方方案对比

| 项目 | 当前 DIY sample | 官方推荐流程 |
|---|---|---|
| 板端输出 | 固定时长、命令控制的 CSV | 持续转发原始传感器数据 |
| 标签方式 | `label <name>` 命令 | Desktop app 中标注录音片段 |
| 数据切分 | PC 脚本按文件保存，切分能力有限 | Dataset Builder 自动切分和清洗 |
| 数据格式 | 需要自定义脚本转换 | 官方工具生成上传格式 |
| 适用场景 | bring-up、快速 PoC | 正式数据集和模型训练 |
| 维护成本 | 项目自行维护协议和脚本 | 跟随 Nordic 官方工具链 |

## 6. 分阶段实施计划

### 阶段 A：确认官方工具链

1. 下载并运行官方 Data Collection Firmware/Data Forwarder。
2. 确认 Data Collection Desktop app 能发现并连接目标设备。
3. 确认 XIAO nRF54LM20B 的 USB CDC 或其他传输接口与官方协议兼容。
4. 使用官方 Dataset Builder 生成一个包含 `idle` 和 `swipe_left` 的最小数据集。

### 阶段 B：适配 XIAO nRF54LM20B

1. 若官方 firmware 不直接支持 XIAO nRF54LM20B，复用当前 IMU 驱动和 USB CDC 配置。
2. 将板端输出格式调整为 Data Forwarder 所需的协议和字段。
3. 保留 100 Hz 采样率、六轴顺序和与板端推理一致的单位。
4. 用 Desktop app 和 Dataset Builder 完成端到端验证。

### 阶段 C：替换正式文档与示例入口

1. 将官方工具链作为 README 的首选数据采集方式。
2. 将 DIY sample 标记为 PoC/底层通信验证工具。
3. 保留 `prepare_dataset.py` 作为离线兼容工具，但不再作为官方推荐流程。
4. 使用官方 Dataset Builder 输出的数据训练并导出模型，再回到板端验证。

## 7. 训练验证注意事项

- 第一次跑通流程可以使用 Edge AI Lab 自动 Holdout Validation（80% 训练、20% 验证）。
- 只有在拥有独立录音批次或独立操作者数据时，才上传单独的 Holdout Dataset。
- 分类任务至少需要两个类别，每个类别至少 20 个样本；正式模型还应包含 `idle` 和
  `unknown`，避免把非目标动作误判为目标手势。
- 训练时的传感器顺序、采样率、单位和板端推理必须完全一致。

## 8. 官方参考链接

- [Nordic Edge AI Lab](https://ai.lab.nordicsemi.com)
- [Edge AI Lab documentation](https://docs.nordicsemi.com/bundle/edge-ai-lab)
- [Preparing data for gesture recognition](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/get_started.html/preparing-raw-dataset)
- [Dataset requirements](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/model_creating_pipeline/dataset_requirements.html)
- [Uploading dataset](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/model_creating_pipeline/data_uploading_and_setup.html/uploading-dataset?contentId=6zSAGeHVkrQiNvIvmSG0FA)
- [Data Forwarder sample](https://nrfconnectdocs.nordicsemi.com/addons/addon-edge-ai/latest/samples/data_forwarder/README.html)
- [Compile a model for the Axon NPU](https://docs.nordicsemi.com/r/bundle/edge-ai-lab/page/compile_model.html/compile-for-axon-npu)

## 9. 当前结论

当前 DIY sample 已完成 USB CDC 数据采集和离线数据集整理验证，但它应被视为早期
验证工具。正式数据采集应迁移到 Nordic 官方 Data Forwarder、Data Collection Desktop
app 和 Dataset Builder，以降低数据标注、切分、清洗和格式兼容方面的维护成本。
