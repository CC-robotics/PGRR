# 学生复现预期输出

这里描述产物契约，不规定“必须得到更好结果”。数值随实现和 seed 变化；禁止为匹配
示例而改结果。

## 保留的可运行资源

学生分支保留：

- `scenarios/` 中的固定 train/validation/test 场景和预览；
- `data/interim/` 中已纳入版本控制的小型 HDF5 shard；
- `checkpoints/bc/`、`checkpoints/dagger/` 中的小型 baseline checkpoint；
- 原有 `tests/unit/`、`tests/integration/`、`tests/regression/`；
- Arena 安装/构建脚本和经典 planner baseline；
- 论文框架、数据驱动图表脚本和已记录配置。

Base classical planner 不依赖学生 A*、专家代价或 BC 训练循环，因此可先运行 baseline。
恢复学习链在相应 TODO 完成后逐步恢复。

## 作业产物目录

建议使用下列路径，避免覆盖教师/最终产物：

```text
outputs/student/
├── astar_demo.pdf
├── subgoal_demo.pdf
├── failure_timeline.pdf
├── expert_costs.pdf
├── bc_smoke/
│   ├── best.pt
│   ├── config.yaml
│   └── metrics.json
├── offline_policy_ablation.csv
├── offline_policy_ablation.pdf
├── final_outcomes_by_density.pdf
└── failure_case.md
```

## 最低字段

BC `metrics.json` 至少记录：seed、配置、epoch、loss、top1、top3、invalid rate、expert cost
regret、dataset hash 和 checkpoint hash。消融 CSV 至少记录 model、mask mode、sample
count、top1/top3、invalid rate、regret、near-optimal/catastrophic rate 和两个 SHA256。

每张图的提交说明包含生成命令、输入文件、Git commit 和一句“图支持/不支持什么结论”。

## 完成条件

```bash
ruff check packages tests/student scripts/evaluate scripts/paper
pytest tests/unit tests/student -q
```

ROS/Arena 集成测试依机器 profile 单独运行。若无可用 GPU，BC 和小数据 DAgger 使用 CPU；
PPO 仅做 smoke 也必须明确标注，不能冒充完整训练。
