# 作业二：模块化前的合成测试样例计划

日期：2026-08-28  
状态：测试设计；未迁移任何生产代码，未运行正式训练或最终评测。

## 1. 目的

第一次模块化不应直接以 Gazebo 场景验证。仿真中同时含有地图、传感器、Nav2 和时序因素；若结果不同，很难定位是重构还是环境波动造成的。

因此先用“小而固定”的合成输入检验重构前后每一步动作掩码与最终动作是否一致。它像给计算器输入固定数字核对答案，确认正确后才把它放回机器人系统。

## 2. 可复用的现有基础

仓库已经有合适的单元测试基础，因而不需要另起一套测试框架：

- `tests/unit/test_recovery_options.py` 已覆盖重复 WAIT、BACKUP、REPLAN、净后退和 `ensure_safe_wait_fallback`；
- `tests/unit/test_ramp_ml.py` 已构造固定 `RecoveryObservation`，并验证 ONNX 的 `lidar=(5,180)`、`state=(53,)`、`mask=(25,)`；
- `tests/unit/test_baseline_profiles.py` 已检查恢复节点中关键约束的调用顺序。

首次实现时，可新增一个独立测试文件，例如
`tests/unit/test_decision_coordinator.py`，不依赖 ROS、Docker 或 Arena。

## 3. 固定样例夹具

### A. 基线观测 `normal_observation`

- LiDAR：5 帧、每帧 180 个正数距离；
- 目标极坐标：`[2.0, 0.2]`；
- 局部路径：8 个二维点；
- 速度、基础规划器动作、10 步进度历史、10 步角速度历史；
- `PlannerStatus.ACTIVE` 与一个明确的 `FailurePrediction`。

这与现有 `test_ramp_ml.py` 中的固定观测契约一致，避免模型输入形状在重构时被无意改变。

### B. 掩码 `mask_with_escape`

初始允许一个临时子目标、WAIT、BACKUP、REPLAN。用于验证各种预算约束按顺序收紧。

### C. 掩码 `mask_wait_only`

只有 WAIT 为真，模拟没有可靠移动方向的近障情况。任何组合约束后仍必须是 WAIT，不能因此“恢复”一个平移动作。

### D. 可控策略 `fake_policy`

策略不读取真实 ONNX，而是在合法动作里确定地选指定 ID；测试中记录它收到的最终掩码。这样能把“规则是否正确”和“模型是否预测正确”分开。

## 4. 第一批用例

| 用例 | 输入状态 | 关键断言 |
|---|---|---|
| C01 正常恢复 | 全部预算未耗尽 | 最终 mask 与当前实现一致；fake policy 只从合法动作中选择 |
| C02 空掩码 | 全 False | 结果仅保留 WAIT |
| C03 重复等待 | WAIT 次数达到预算，存在子目标 | WAIT 被移除，子目标保留 |
| C04 无逃离动作时重复等待 | 仅 WAIT / CONTINUE | WAIT 不可被移除 |
| C05 重复 BACKUP | 后退次数达到预算，存在子目标 | BACKUP 移除，子目标仍合法 |
| C06 重复 REPLAN | 重规划次数达到预算，存在替代动作 | REPLAN 移除，不影响其他合法动作 |
| C07 组合极端情况 | REPLAN/BACKUP 先被预算移除，净后退再移除子目标 | 结果安全回落为 WAIT；对应既有回归用例 |
| C08 ONNX 接口守护 | `normal_observation` 与 25 位 mask | 编码后保持 `(5,180)`、`(53,)`、`(25,)` |

## 5. 比较方式

每一例应先在“重构前的 helper 调用序列”得到 `expected_mask` 和
`expected_action_id`，再调用新协调器，并断言：

```text
new_mask        == expected_mask
new_action_id   == expected_action_id
new_memory      == expected_memory
```

遥测字符串不宜逐字符锁死（它会妨碍合理的格式改进）；更稳妥的是检查核心字段，例如 `bc_yield_mask`、`bc_recurrent_escape` 是否存在以及动作 ID 是否一致。

## 6. 实施后必须执行的回归范围

```powershell
$env:PYTHONPATH = "$PWD\packages\ramp_core;$PWD\packages\ramp_ml"
python -m pytest -q tests/unit/test_recovery_options.py tests/unit/test_action_mask.py tests/unit/test_state_machine.py tests/unit/test_ramp_ml.py tests/unit/test_baseline_profiles.py
```

合成测试全通过，只说明**重构没有改变既有逻辑的可测试部分**；它不构成新算法效果，也不能替代 Arena 的 smoke 检查。是否实际开始代码迁移，仍等教授确认。
