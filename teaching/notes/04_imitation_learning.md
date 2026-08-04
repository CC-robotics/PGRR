# 第 4 讲：规划专家与模仿学习

## 特权短时域专家

专家对每个合法恢复动作进行约 2.5--3 s rollout。它可使用静态地图、机器人真值和
行人真实状态；未来轨迹不可用时采用常速度外推并随时间增加安全膨胀。专家只用于
训练标签和 Oracle，不部署到正式测试。

总代价包含 collision、progress、social、rejoin、length、smooth、time、switch 和
repeat-WAIT。碰撞代价远大于其他项，masked action 代价为无穷。WAIT 有时间和重复
代价，避免“永远不动”成为虚假安全策略。

Assignment 4 实现：

```text
J_progress = w_progress * max(0, progress_penalty)
J_rejoin   = w_rejoin   * max(0, distance_to_original_path)
```

负输入按零处理，防止错误数据变成奖励。修改后运行专家单元测试，观察空旷场景是否
偏向有进展的动作，以及 head-on 场景是否避开碰撞 CONTINUE。

## Behavior Cloning

策略网络将 5x180 LiDAR 输入 1D CNN，将目标、局部路径、速度、base action、历史和
planner status 输入 MLP，拼接后输出 25 logits。action mask 在 softmax 前应用。

普通 BC 最小化专家动作的交叉熵。margin-weighted BC 用专家第一与第二动作代价差
增加明确样本权重，但权重必须裁剪。PGRR 的最终选择是否使用 margin weighting 由
validation 结果决定，不能因为方法名字而预设有效。

## Assignment 5 训练循环

每个 batch：搬到 device、forward、计算选定损失、可选反向传播、梯度裁剪、optimizer
step，并按样本数累计七个指标。validation 传 `optimizer=None`，不得更新权重。空
DataLoader 必须报错。

除 top-1/top-3 外，还报告 invalid-action rate、专家 cost regret、near-optimal rate 和
catastrophic-action rate。高 accuracy 不一定带来低闭环碰撞，因此还需 Arena rollout。

## 小数据练习

使用仓库内小型 HDF5 和 smoke 配置，固定 seed。记录 checkpoint hash、配置和最佳
validation epoch。不要用 test split 选 epoch。

```bash
pytest tests/unit/test_ramp_ml.py tests/unit/test_hdf5_schema.py -q
make train-bc EXPERT_DATASET=<small.h5> BC_CONFIG=<smoke.yaml>
```
