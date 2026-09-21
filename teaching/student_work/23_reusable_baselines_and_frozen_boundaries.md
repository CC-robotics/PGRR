# 后续实验准备：可复用基线与冻结边界清单

日期：2026-08-28  
状态：根据项目 README、配置布局和最终 evidence 的只读整理；没有改动任何基线、模型或发布产物。

## 1. 为什么先区分“可复用”和“不可修改”

后续实验需要复用已有系统，才能把精力放在新场景或新方法上；但复用不等于可以修改已发布证据。最安全的做法是把原项目视作一个可靠基线，同时在新的 benchmark ID、输出目录和 manifest 下开展独立实验。

## 2. 可复用的系统组成

| 层次 | 可复用内容 | 在新实验中的作用 |
|---|---|---|
| 在线环境 | Ubuntu 22.04、ROS2 Humble、Arena Gazebo、Jackal、Nav2 DWB、planar LiDAR | 保持机器人与导航栈一致，减少环境差异。 |
| 经典对照 | `base`（Base DWB）、`standard`（Nav2 标准恢复） | 给新场景提供无学习/标准恢复的参照。 |
| PGRR 对照 | `heuristic`、`bc_uniform`、`pgrr` | 比较规则恢复、BC 与验证选择的 DAgger 恢复。 |
| 动作与安全接口 | 21 个临时子目标 + WAIT/BACKUP/REPLAN/CONTINUE；规划掩码与安全 WAIT 回退 | 固定“能做什么”，新场景只改变环境条件。 |
| 数据与分析 | expert 标注、BC/DAgger 训练脚本、结果收集、配对统计、制图流程 | 让新数据能沿用同一证据链。 |
| 回归检查 | `make preflight`、`make build`、`make smoke` 与 Python 单元测试 | 在改场景/重构前后检查基础设施和核心逻辑。 |

## 3. 必须保持冻结、不可作为调参对象的内容

| 项目对象 | 冻结原因 | 正确做法 |
|---|---|---|
| `outputs/moderate/final/` | 已发布的最终表格、哈希与论文证据 | 只读引用，不新增、不替换、不重算其中行。 |
| `scenarios/splits/moderate_v6_test.yaml` | 已封存 held-out test | 不用它选择阈值、checkpoint 或新场景参数。 |
| `checkpoints/final/best.onnx` | 发布时验证选择的模型 | 保持原样；新训练保存到新目录。 |
| `configs/final/ei_gazebo.yaml` 的发布身份 | 对应冻结运行环境 | 新实验如需参数变化，复制到独立配置并记录差异。 |
| 原发布结果的统计结论 | 来自 600 个已完成逻辑 episode | 不与新实验的行混合或合并显著性检验。 |

## 4. 新实验应怎样命名和存放

下面是建议的隔离结构，名称仅作模板，实际 benchmark 名称由教授确认：

```text
configs/experiments/student_extension_<name>.yaml
scenarios/splits/student_extension_<name>_{train,validation,test}.yaml
data/interim/student_extension_<name>/
checkpoints/student_extension_<name>/
outputs/student_extension_<name>/
  episode_manifest.parquet
  run_manifest.json
  results.parquet
  summary.csv
  pairwise_statistics.json
```

发布目录 `outputs/moderate/final/` 不在此结构中。

## 5. 公平对比的最低要求

1. 每个方法有完全相同的 `condition_key` 集合；
2. 同一条件的地图、起终点、障碍物、行人轨迹、密度和 seed 均一致；
3. 经典与学习方法接受相同的终止规则、时间上限和日志格式；
4. 新训练只使用新实验的 train，模型选择只看 validation；
5. 新 test 在配置、场景、checkpoint、并发与统计规则锁定后再打开；
6. 结果同时报告安全、完成和效率/平滑性，而不是只展示一个优势指标。

## 6. 当前可以安全继续的工作

- 设计独立场景参数和 split 模板；
- 完善日志/结果字段、配对检查和论文图稿；
- 做不改变算法语义的重构设计与合成回归测试计划；
- 对已提交 manifest、配置和 checkpoint 做只读核对。

正式创建场景、确定训练范围、开始代码迁移或运行大规模实验前，需要教授确认研究问题和优先级。
