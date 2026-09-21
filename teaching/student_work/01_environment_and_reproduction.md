# 环境与复现记录（起始审计）

日期：2026-08-18  
目的：先记录真实环境和已完成验证；未通过的项目不得写成“已复现”。

## 当前机器事实

| 项目 | 结果 |
|---|---|
| 操作系统 | Windows（当前工作目录为 Windows 路径） |
| 当前 Python | 3.13.12 |
| 离线 Conda 环境 | `.conda/ramp-offline`，Python 3.10.20；项目路径含空格，Conda 已给出警告 |
| `make` / `bash` | 当前 PowerShell 中不可用 |
| WSL | `wsl.exe` 可用，但尚未检查或安装 Ubuntu/ROS2/Arena |
| ROS2 Humble / Arena Gazebo | 未验证，不能声称已安装 |

## 已执行的检查

```powershell
python -m pytest tests/unit/test_astar.py -q
python -m ruff check packages/ramp_core/ramp_core/planning/astar.py
```

初始系统 Python 缺少 `pytest` 和 `ruff`。项目内环境安装时，pip 最后因 Windows 的
`WinError 32`（`mpmath` 文件被占用）使 Conda 报告失败；但关键离线依赖已经实际安装。
该环境现已用于目标 A* 测试。完整项目测试仍须在后续单独验证。

## 已通过的最小验证

在 PowerShell 中为本次运行临时设置包路径：

```powershell
$env:PYTHONPATH = "$PWD\packages\ramp_core;$PWD\packages\ramp_ml"
.\.conda\ramp-offline\python.exe -m pytest tests/unit/test_astar.py -q
.\.conda\ramp-offline\python.exe -m ruff check packages/ramp_core/ramp_core/planning/astar.py
.\.conda\ramp-offline\python.exe -m ruff format --check packages/ramp_core/ramp_core/planning/astar.py
```

结果：A* 单元测试 `2 passed in 1.35s`；Ruff 检查通过；格式检查通过。恢复动作空间测试
也通过：`2 passed in 0.35s`，其 Ruff 与格式检查也通过。该结果只证明当前参考实现的
两个纯 Python 模块在可用的最小离线环境中通过验证，不等同于完整项目或仿真复现。

## 复现分级

| 层级 | 当前状态 | 完成标准 |
|---|---|---|
| 静态阅读 | 已开始 | 能解释 A*、DWB、BC、DAgger 与 PGRR 的分工 |
| A* 离线单元测试 | 已通过 | 2 项测试通过；Ruff 与格式检查通过 |
| 恢复动作空间离线单元测试 | 已通过 | 2 项测试通过；Ruff 与格式检查通过 |
| 失败检测离线单元测试 | 已通过 | 44 项测试通过；Ruff 与格式检查通过 |
| 专家规划与动作 mask 测试 | 已通过 | 37 项测试通过；Ruff 与格式检查通过 |
| BC 与 HDF5 schema 测试 | 已通过 | 10 项测试通过；Ruff 与格式检查通过 |
| DAgger 聚合脚本 | 已验证入口 | `--help`、Ruff 与格式检查通过；未在参考分支启动训练 |
| BC 小数据训练 | 已通过 | CPU、seed 0、12 epoch；ONNX 导出及 ONNX checker 通过 |

## BC 小数据训练记录

命令使用 `data/interim/temporary_blockage_finite2_expert_smoke.h5` 与
`configs/imitation/bc_smoke.yaml`，结果输出到 `outputs/student/bc_smoke/`。它使用单一
数据集的随机训练/验证划分，因此只是数据管线 smoke，不是论文证据。

| 字段 | 值 |
|---|---:|
| device | CPU |
| seed | 0 |
| epoch | 12 |
| 训练样本 | 135 |
| 验证样本 | 34 |
| 最后一轮验证 top-1 | 0.9118 |
| 最后一轮验证 top-3 | 0.9706 |
| 最后一轮验证 invalid rate | 0.0000 |
| 最后一轮验证专家代价 regret | 0.0227 |

产物：`best.pt`、`best.ts`、`best.onnx`、`metrics.json`、`config.yaml`。`best.onnx` 已经
通过 `onnx.checker.check_model` 验证。PyTorch 在导出期间给出 legacy ONNX exporter 的
弃用警告；这是版本兼容提示，不是训练或导出失败。

## 单样本推理解释

使用 `best.pt` 对 smoke 数据集的第 0 条样本进行只读推理。共有 25 个候选恢复动作，
其中 action mask 允许 7 个，屏蔽 18 个。专家与模型都选择 action 12：机器人坐标系
下距离 1.0 m、角度 +60° 的临时子目标。模型对该动作的概率为 0.3939；次优候选为
`WAIT`（0.3271）。专家代价分别为 2.6032 和 2.6895。

该例说明：模型不是在所有 25 个动作中任意选分数最大的动作；先由 action mask 删除
不可执行/不安全动作，再在剩余动作中作选择。它是对一条离线样本的解释，不是闭环安全结论。
| 全部离线测试 | 未验证 | 完整依赖安装和 `make test`/等价命令仍待验证 |
| 小数据复现 | 未开始 | `make reproduce-small SEED=0` 成功并保存日志 |
| 文档/论文重建 | 未开始 | 从受支持环境执行 `scripts/reproduce_paper.sh` |
| Arena 闭环仿真 | 未开始 | Ubuntu 22.04 + ROS2 Humble + 固定 Arena 运行时通过 smoke |

## 在线恢复链路复现（2026-08-21）

已在 WSL2 的原生工作副本 `~/PGRR-online` 中完成在线运行时验证。该副本用于
Linux/Docker/Arena，不与 Windows 下的离线 Conda 环境混用。

| 检查 | 命令 | 真实结果 |
|---|---|---|
| Arena 运行时 | `make arena` | 成功；使用隔离 Docker profile |
| ROS 工作区构建 | `make build` | 成功；`ramp_msgs`、`ramp_ros`、`ramp_bringup` 共 3 个包完成 |
| Arena 基础冒烟 | `make smoke SEED=0 HEADLESS=1` | 通过；时钟、TF、LiDAR、里程计和导航 action 均可用 |
| 恢复管理器集成冒烟 | `scripts/arena/smoke_recovery_manager.sh` | 通过；临时目标 `(0.9660, 0.5000)` 被发布，随后原始目标恢复为 `(5.0, 0.0)`；共产生 5 个决策 |

恢复管理器测试的关键输出为：`PASS recovery manager ROS smoke`。输出中的
`incompatible QoS` 是测试订阅端发现的兼容性警告；测试仍然完成并返回 PASS，不能把它
记为失败。

该结果证明了一个小型、可控的在线恢复链路：恢复节点能够发布临时目标、执行有边界的
恢复，并重新发布原始导航目标。它**不是** 600 次冻结测试，也不构成新的论文实验结果。

## 下一步环境步骤

1. 在 WSL2 安装 Ubuntu 22.04，或使用实验室提供的 Ubuntu 22.04 主机。
2. 建立 Python 3.10 Conda 环境 `ramp-offline`，严格按照 `environment.yml`、
   `environment.lock.yml` 和 `requirements-offline.lock.txt` 安装离线依赖。
3. 在不 source ROS 的离线 shell 中运行：

   ```bash
   make test
   make reproduce-small SEED=0
   ```

4. 已在**未激活 Conda** 的 Ubuntu ROS shell 中完成以下运行时验证；以后环境变更后可
   重新执行：

   ```bash
   make arena
   make build
   make smoke SEED=0 HEADLESS=1
   ```

5. 不使用冻结的 `moderate_v6_test` 划分调阈值、选 checkpoint 或试错。

## 证据记录模板

每次运行在本文件追加：日期、Git commit、命令、退出码、环境、输入数据哈希和输出路径。
若失败，还要记录错误信息与下一步验证方式。
