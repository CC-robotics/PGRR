# 作业二：最小重构的回归测试矩阵

目的：后续拆分 `RecoveryObservationBuilder` 和 `RecoveryDecisionCoordinator` 时，证明只是改善工程结构，而没有改变 PGRR 的恢复行为。

## 重构前基线命令

在离线环境、Git 根目录运行：

```bash
set PYTHONPATH=%CD%\packages\ramp_core;%CD%\packages\ramp_ml
.conda\ramp-offline\python.exe -m pytest -q ^
  tests/unit/test_action_mask.py ^
  tests/unit/test_state_machine.py ^
  tests/unit/test_recovery_options.py ^
  tests/unit/test_ramp_ml.py
```

在线 ROS/Arena 环境另运行：

```bash
scripts/arena/smoke_recovery_manager.sh
```

> Windows 的 `^` 是换行符；也可以把 pytest 文件名写在同一行。

## 不变量 → 测试映射

| 必须保持不变 | 主要测试/证据 | 重构后如何判断 |
|---|---|---|
| 25 个动作的编号与特殊动作语义 | `test_recovery_options.py`、`test_action_mask.py` | 相同输入产生相同 mask；特殊动作仍可被正确过滤/保留 |
| 状态机转换 | `test_state_machine.py` | NORMAL / RECOVERY / REJOIN 的状态与原因一致 |
| 恢复预算、等待、后退、侧向承诺 | `test_recovery_options.py` | 同一序列得到相同动作、临时目标、终止原因 |
| ONNX/HDF5 形状 | `test_ramp_ml.py` | LiDAR `(5,180)`、状态 `(53,)`、mask `(25,)` 不变 |
| 任务目标恢复 | `scripts/arena/smoke_recovery_manager.sh` | 临时目标发布后仍能恢复原始目标 |
| ROS 接口/配置 | `test_baseline_profiles.py`、ROS smoke | topic、frame、参数键、`use_sim_time` 不变 |

## 推荐的最小提交顺序

1. 先运行上面的基线测试，保存输出至 `outputs/student/refactor_baseline/`。
2. 仅抽取 `RecoveryObservationBuilder`，不改变 node 的调用时序。
3. 添加“同一合成输入下，旧/新观测字段相同”的单元测试。
4. 再抽取 `RecoveryDecisionCoordinator`，新增“同一输入下，动作 ID、临时目标、reason 相同”的测试。
5. 每一个小提交都重新运行离线单元测试；最终再运行 ROS smoke。
6. 只有全部通过，才开始考虑拆分 `recovery/options.py`；不要在同一次提交中混入算法阈值修改。

## 当前边界

这是一份**实施前的验收矩阵**。尚未改动参考算法源码，也未创建任何新的 ROS 节点模块；因此不能宣称“重构已完成”。

## 已记录的重构前离线基线

2026-08-28 使用项目离线 Python 环境执行本页列出的四个单元测试文件：

```text
179 passed in 4.26s
```

该结果是今后首个纯结构重构提交的最低回归基线；ROS smoke 仍应在 WSL/Arena 环境中单独复跑。
