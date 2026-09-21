# 作业二：观测构建器输入所有权修复

## 发现的问题

在准备把 `RecoveryObservationBuilder` 用于默认关闭的 runtime shadow 前，检查了
它对可变输入的副作用。`RecoveryObservation` 会把内部 NumPy 数组设为只读；原来
builder 对 `base_action` 只调用 `np.asarray`，当输入本身已经是 `float32` 数组时，
它可能与控制器共享同一块内存，并把控制器的原数组也意外设为只读。

这不会影响已完成的离线等价性数字，但如果直接接入 ROS shadow，诊断候选路径
就可能反过来改变权威运行状态，违反 shadow 的基本边界。

## 修复

builder 现在对 `base_action` 显式 `.copy()`，与旧 inline 实现保持一致。新增测试
同时检查：

- 构建后原 `base_action` 仍可写；
- 原 LiDAR scan 仍可写；
- 修改两个原输入不会改变已经构建的 observation；
- observation 本身仍遵守不可变数据契约。

修复后，builder、shadow comparator 和等价性 probe 共 13 项测试通过；seed
92001 的 32 个边界用例仍为 32/32 exact equivalent，七字段最大误差为 0。

## 边界

这是输入所有权与副作用修复，不是算法修改。ROS 尚未接入 shadow，也没有产生
新的导航结果；冻结模型、阈值和最终证据均未触碰。
