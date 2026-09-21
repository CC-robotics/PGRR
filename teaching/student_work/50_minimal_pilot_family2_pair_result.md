# 八类最小配对试运行：第 2 类结果

2026-09-09 在同一个固定的“遮挡侧出现”训练场景上完成 Base/PGRR 配对。

| 方法 | 结果 | 样本数 | 终止时物理目标距离 |
|---|---|---:|---:|
| Base | COLLISION | 516 | 9.991 m |
| PGRR | TIMEOUT | 900 | 10.507 m |

这一个开发样例中，PGRR 避免了 Base 的碰撞，但没有到达目标，因此只能称为“安全结果改善、完成性仍不足”，不能称为完整成功。

PGRR 的恢复链确实运行了：第一次约在 50.82 s 进入 `EMERGENCY_STOP`，随后进入 `PENDING_RECOVERY`、`RECOVERY`、`REJOIN` 并回到 `NORMAL`；完整恢复并恢复原目标共发生 3 次，末尾又开始第 4 轮恢复。全程共有 27 个决策事件，包括 WAIT 7 次、BACKUP 9 次和 CONTINUE 11 次；没有选择 21 个临时子目标中的任何一个。

需要注意，Base outcome 的 detail 是“机器人轮廓与已知静态场景几何相交”，而不是明确的动态行人碰撞。因此这条结果证明 PGRR 的恢复链改变了结局，但尚不能单独证明“遮挡行人碰撞被解决”。后续分析必须区分静态障碍碰撞与动态行人碰撞。

原始 JSONL、metadata、outcome 仍保存在 WSL 的 `/home/preface/PGRR-online/data/raw/`。自动收集器已把其哈希、outcome 和恢复摘要写入 `outputs/student/eight_family_pilot/pair_results/f01_occluded_side_emergence.json`。

本结果只属于未完成的开发 pilot。目前只完成 2/8 对，不能计算或宣称总体优越性。
