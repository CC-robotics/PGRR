# 八类最小配对试运行：第 1 类结果

2026-09-09 在同一个固定的“斜向切入”训练场景上，Base 和 PGRR 各运行一次。二者使用相同 JSON、相同种子 91000；episode ID 和输出互不覆盖。

| 方法 | 结果 | 样本数 | 终止时物理目标距离 |
|---|---|---:|---:|
| Base | TIMEOUT | 900 | 0.692 m |
| PGRR | TIMEOUT | 901 | 0.865 m |

PGRR 轨迹中只有一次 `CONTINUE/not_triggered` 决策，恢复状态始终为 `NORMAL`，没有临时子目标，也没有发生原目标恢复事件。因此这次结果不能解释成“PGRR 恢复失败”，更准确的说法是：**当前第 1 类单例没有触发 PGRR，且 Base/PGRR 都在目标附近超时，区分度不足。**

这条负结果已经保留在 `outputs/student/eight_family_pilot/pair_results/f00_diagonal_cut_in_corridor.json`，并绑定 WSL 原始 JSONL、metadata 和 outcome 文件的 SHA-256。它只属于开发试运行，不能用于优越性或统计显著性结论。

运行器在首次实跑前暴露了一个 Windows TSV 行尾问题：`ROS_DOMAIN_ID` 末尾带隐藏的 CR。启动脚本在进入仿真前拒绝该值，所以没有产生错误 episode。现已兼容 CRLF，并把新生成计划固定为 LF 字节。
