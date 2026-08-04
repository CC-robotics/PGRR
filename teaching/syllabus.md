# PGRR 动态社会导航复现课程

PGRR（Planning-Guided Recovery and Rejoin）是一套失败触发的动态导航恢复系统。
正常状态由经典局部规划器控制；只有碰撞风险、冻结、振荡或动态死锁出现时，
恢复模块才从 21 个临时子目标以及 WAIT、BACKUP、REPLAN、CONTINUE 中选择动作。
仓库中的 Python 包为兼容既有代码仍使用 `ramp_core`、`ramp_ml` 名称。

## 面向对象与先修知识

课程面向完成过 Python、线性代数和概率论基础课的本科二年级学生。ROS2、A*、
模仿学习和统计检验从可运行例子开始讲，不要求已有机器人项目经验。建议每组
2--3 人，并保证每个人都能独立解释自己的实现。

## 学习目标

完成八周课程后，学生应能：

1. 区分 ROS2/Arena 在线环境与 Conda 离线环境，并解释为何不能混装；
2. 实现确定性的栅格 A* 和机器人坐标到世界坐标的恢复子目标变换；
3. 从有时间戳的可观测历史检测 freeze 和 oscillation；
4. 解释特权规划专家的代价项、action mask 和训练/测试信息边界；
5. 实现 action-masked Behavior Cloning 训练循环；
6. 解释 DAgger 如何缓解协变量偏移，以及 PPO 微调可能产生的 reward hacking；
7. 使用固定 episode manifest、配对统计和失败分类完成一次可审计实验；
8. 从 CSV/Parquet 自动生成论文图，而不是手工填写结果。

## 分支与安全边界

- 完整实现保存在 `teacher/reference`，学生作业分支为 `student/reproduce`。
- 教师默认在干净的 `teacher/reference` 上运行
  `scripts/teaching/make_student_branch.sh`。若源工作树包含必须保留的本地文件，可显式使用
  `--allow-source-dirty`；学生分支仍只取已提交的 `teacher/reference` HEAD，脚本不会
  stash、reset、覆盖源文件或切换调用者分支。
- 学生不得把仿真真值行人状态加入正式策略观测，也不得修改 test split 调参。
- 禁止删除失败 episode；模拟器失败必须单独分类并说明排除依据。
- 不得声称 PPO、Gazebo 或统计显著性已经完成，除非对应原始产物存在。

## 八周安排

| 周 | 主题 | 实现任务 | 可演示产物 |
|---:|---|---|---|
| 1 | ROS2、Arena 与时间/坐标系 | 环境检查、运行经典 baseline | 一段带 `/clock`、TF、LiDAR 的运行记录 |
| 2 | A*、DWA/DWB 与恢复动作 | Assignment 1--2 | A* 路径图和临时子目标 demo |
| 3 | 失败检测 | Assignment 3 | freeze/oscillation 时间序列图 |
| 4 | 特权专家与 BC | Assignment 4--5 | 专家 rollout 图和一次小型训练 |
| 5 | DAgger | 分布偏移分析 | 迭代前后动作/状态分布图 |
| 6 | PPO 与安全约束 | 阅读和 smoke 分析，不要求大训练 | reward 分解与失败案例 |
| 7 | 实验设计与统计 | Assignment 6 | 配对消融 CSV 与解释 |
| 8 | 论文证据链 | Assignment 7 | 自动生成矢量结果图和短报告 |

## 每周提交要求

每周提交一个小型 PR，必须包含：

- 一个可运行 demo 的命令和退出状态；
- 至少一个新增或修正的测试；
- 一张由脚本生成、标明数据来源的图；
- 一段 2--3 分钟口头解释提纲；
- 一个失败案例，说明现象、证据、根因假设和下一步验证。

PR 不接受截图中的代码、手工修改的结果表、无法追溯 seed 的实验，或只展示成功案例。

## 评分

| 项目 | 比例 | 主要判据 |
|---|---:|---|
| 正确性与测试 | 35% | 公共测试、边界条件、确定性 |
| 实验可复现性 | 20% | seed、配置、manifest、原始日志 |
| 工程质量 | 15% | 类型、文档、错误处理、不破坏环境 |
| 图表与分析 | 15% | 数据驱动、坐标完整、结论不过界 |
| 解释与协作 | 15% | PR、口头提纲、失败复盘、代码归属清晰 |

## 推荐工作流

```bash
git switch student/reproduce
conda run -n ramp-offline pytest tests/unit/test_astar.py -q
conda run -n ramp-offline pytest tests/student/test_student_tasks.py -q
conda run -n ramp-offline ruff check packages tests/student
```

先运行与当前作业对应的小测试，再运行全部离线测试。经典 DWB baseline、固定场景、
小型 HDF5 数据和已训练 checkpoint 保留在学生分支中；大型仿真和训练不作为每周
作业的前置条件。

## 学术诚信

可以讨论思路和阅读 `teacher/reference` 生成的论文，但作业期间不得从教师分支复制
目标函数实现。使用外部代码必须注明来源和许可证。结果不理想是可接受结论；删除
失败样本、伪造日志或手工改表不是。
