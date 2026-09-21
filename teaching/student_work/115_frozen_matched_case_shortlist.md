# 115 从完整冻结结果中筛选 8 个论文案例候选

> 口径更正（2026-09-16）：本文件中的 8 行是从冻结结果中选出的 8 条
> 单次条件/episode 定性例子，不是教授要求的 8 个场景，也不计入八场景完成数。
> 它们只用于辅助解释完整 120 条件统计结果。

## 为什么改走这条路线

新做的 lead-stop 与 open closing-gap 都没有满足“Base 失败、PGRR 到达”的晋级门。继续反复改场景容易变成按结果调参。与此同时，已经完成并冻结的 600 回合正式实验本身包含 120 个匹配条件，因此本轮只读检查这些既有证据，不重跑测试、不改变算法。

## 只读发现

- 共有 26 个匹配条件满足：Base 未到达、PGRR 到达；
- 这些条件分布在 5/8 个正式场景族：`blind_corner`、`crossing_flow`、`doorway_bottleneck`、`head_on_corridor`、`temporary_blockage`；
- `group_blocking`、`opposite_streams`、`overtaking` 中 Base 与 PGRR 均为 15/15 到达，因此这三族不能用来展示 PGRR 相对 Base 的成功差异；
- 已按可复现规则选出 8 条定性例子，覆盖上述 5 个有效机制族，每族最多两个，并优先选择其他对照方法也失败的条件。

最强的一个定性案例是 `blind_corner / medium / replicate 4 / seed 87314`：Base 与 Standard 碰撞，Heuristic 与 Uniform BC 规划失败，只有 PGRR 到达。

## 论文边界

这 8 行是从最终结果中事后筛选的**定性案例**，适合做轨迹图、恢复时间线和机制解释，不能伪装成八个预注册独立统计结论。正式性能结论仍必须使用完整 120 对条件及既有 Holm 校正统计。

## 可复现产物

- `scripts/student/select_eight_matched_paper_cases.py`
- `tests/unit/test_select_eight_matched_paper_cases.py`
- `outputs/student/paper_case_shortlist/eight_matched_cases.csv`
- `outputs/student/paper_case_shortlist/eight_matched_cases.json`
- `outputs/student/paper_case_shortlist/eight_matched_cases.md`

Ruff 通过，2 项选择器单元测试通过。这些材料可继续做 outcome/轨迹哈希核对并判断哪些适合画图，但不能用于宣称已经完成“八个场景”。
