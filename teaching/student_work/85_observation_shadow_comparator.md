# 作业二：默认关闭的观测 shadow comparator

## 完成内容

新增纯 Python 模块
`packages/ramp_core/ramp_core/recovery/observation_shadow.py`，用于在不改变当前
ROS 权威观测路径的前提下，对旧 inline 观测与新 `RecoveryObservationBuilder`
的输出逐字段比较。

关键约束：

- 默认 `enabled=False`；
- 关闭时连 candidate factory 都不会执行，避免额外计算或异常影响现有路径；
- 开启时比较七个数组字段的 shape 和最大绝对误差；
- 单独比较 planner status 与 failure prediction；
- 报告固定记录 `authoritative_path_changed=false`；
- 接口不接受 privileged human/simulator state；
- tolerance 必须有限且非负。

现有 32 例离线等价性探针已改为使用该 comparator。seed 92001 的路径长度、
LiDAR 历史和进度历史边界组合仍保持七字段误差全部为 0。

## 验证

- comparator 关闭时不调用 candidate；
- 完全相同观测报告 exact equivalent；
- 0.05 的 base-action 偏差能被检出；
- 负数、NaN、Inf tolerance 均被拒绝；
- builder 与 probe 的相关测试共 11 项通过；
- Ruff 通过。

## 边界

本步没有把 comparator 接入 ROS，也没有替换 `RecoveryManagerNode` 的旧观测
实现。它只是为以后非冻结、默认关闭的运行时 shadow 验证准备了安全比较器；
不能据此声称 ROS callback timing 或实时行为已经等价。
