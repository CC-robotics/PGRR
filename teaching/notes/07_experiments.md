# 第 7 讲：实验协议、配对统计与消融

## 先锁 manifest

所有方法使用同一 episode manifest：地图、场景、密度、seed、起终点和行人配置 hash
完全一致。方法不能自行跳过不利 episode。最终测试前锁定配置、checkpoint hash 和 Git
commit；发现代码 bug 后需要重跑所有受影响方法。

## Split

按地图和场景变体切 train/validation/test，不能随机按帧切。train 用于训练和 DAgger；
validation 用于阈值、模型和 reward 选择；test 只用于锁定后的最终报告。

## 指标

至少同时报告：成功、碰撞、timeout、SPL、时间、最小人距、freeze、oscillation、恢复
触发、恢复成功、恢复时长、干预比例和推理延迟。一个“永远 WAIT”的策略可能碰撞率
低但成功率为零，所以安全与效率必须一起看。

## 配对统计

二元成功结果可用 McNemar；连续配对指标可用 Wilcoxon signed-rank。报告 bootstrap
95% CI、effect size 和样本量，多重比较用 Holm 校正。p-value 大并不证明方法相同；
它也可能表示样本不足。

## Assignment 6

实现离线策略消融指标，并在同一个 validation HDF5 上比较 Uniform BC、候选加权 BC、
DAgger 以及 mask 开/关。mask 关闭行只表示离线 proposal，不允许直接部署危险动作。

必须检查：固定 `[N,25]` shape、每行至少一个合法动作、非有限 regret 的一致处理、输出
dataset/checkpoint SHA256。禁止用 test label 做消融选择。

## 失败分析

把失败分类为人/静态碰撞、开阔/窄道 freeze、oscillation、deadlock、bad/missed trigger、
invalid subgoal、failed rejoin、planner abort 和 repeated recovery。每类选代表 episode，
但数量统计必须覆盖全部 episode。

```bash
pytest tests/unit/test_offline_policy_ablation.py -q
python scripts/evaluate/offline_policy_ablation.py --help
```

作业说明中写清楚“数据支持什么、不支持什么”，这比给出一个更大的百分比更重要。
