# 作业二：观测构建器双路等价探针

## 做了什么

新增 `scripts/student/verify_observation_builder_equivalence.py`，用同一组固定输入分别调用：

1. 从当前 `RecoveryManagerNode._observation` 独立转写的 inline reference；
2. 新增但尚未接入 ROS 的 `RecoveryObservationBuilder`。

探针使用显式种子 `92001` 生成 32 个确定性用例，覆盖空/短/长路径，1/2/5/7 帧
LiDAR，以及 0、短于上限、等于上限和超过上限的距离/角速度历史。输出保存在
`outputs/student/refactor_baseline/observation_builder_equivalence.json`。

## 结果

- 32/32 用例元数据一致；
- `lidar`、`goal_polar`、`path_waypoints`、`robot_velocity`、`base_action`、
  `progress_history`、`angular_velocity_history` 七个数组字段的最大绝对误差均为 0；
- 新探针与 Builder 测试合计 `5 passed`；
- Ruff 检查通过。

## 这说明什么

这证明新 Builder 在覆盖到的纯计算输入上精确复现了当前节点的整形规则，比只看代码
相似更可靠。它仍不证明 ROS 运行时等价：回调更新时序、消息缓存、goal 切换和发布
顺序都没有进入离线探针。因此本步可以把“纯函数行为一致”标为通过，但不能把 ROS
节点改接后的回归门视为已经完成。

## 下一安全步骤

在不删除 inline 逻辑的前提下，可准备一个默认关闭的双路比较适配层：运行时仍使用旧
结果，仅在非冻结开发 smoke 中计算 Builder 输出并报告字段差异。真正替换旧路径必须
等该影子比较无差异后再做。

