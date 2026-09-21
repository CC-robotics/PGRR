# 八类动态社交导航情境：PGRR 扩展实验设计草案

状态：设计草案，待转化为独立 benchmark 的 train/validation 配置。  
边界：不修改冻结的 `moderate_v6_test`、最终 checkpoint 或已发布结果。

## 研究目标（不能写成预设结论）

老师提出的目标可以严谨地表述为：构建八类**机制不同、参数可控且事先定义**的动态交互情境，检验 PGRR 是否比经典规划器和学习型对照更常恢复并完成任务，同时如实报告它没有改善、变慢或失败的情形。

我们不能先挑选“PGRR 必胜”的 episode，再以此证明优势；正确做法是先冻结每个 family 的几何、密度、种子和评价规则，再在相同条件下比较。只有统计结果出来后，才能说“其他方法不能处理”或“效果更差”。

## 统一比较方式

- 同一 scenario JSON、同一随机种子，对每个方法各运行一次；
- 对照：DWB Base、现有启发式恢复、Uniform BC；实验方法：PGRR；
- 每类均保留 GOAL_REACHED、COLLISION、TIMEOUT、PLANNER_FAILURE、SIMULATOR_FAILURE、INVALID_RESET，绝不替换失败回合；
- 主要指标：完成率、碰撞率、超时率；同时报告完成时间、路径长度、角速度 jerk；
- PGRR 的机制检查：是否在可观测失败后触发、临时子目标是否由规划器执行、是否恢复原目标；
- DAgger 仅使用 train；模型/轮次选择仅使用 train + validation；冻结后才生成独立 test。

## 八类情境

| # | 场景族 | 主要变量 | 希望暴露的基线困难 | PGRR 应检验的恢复机制 | 当前状态 |
|---|---|---|---|---|---|
| 1 | `diagonal_cut_in_corridor` | 切入侧、角度、时机、速度 | 前方斜向突然占据局部路径，碰撞风险或急转 | 碰撞风险触发后选择可行临时子目标、再回到原目标 | 已实际 smoke（train 单例） |
| 2 | `occluded_side_emergence` | 遮挡侧、首次可见距离、出现时机、速度 | 行人刚出现即横穿，常态 DWB 来不及重规划 | 可观测风险触发、让行/绕行并 rejoin | 已实际 smoke（train 单例） |
| 3 | `recurrent_bidirectional_crossing` | 双向人数、交叉相位、间隔、密度 | 连续交叉使机器人反复停走，可能振荡 | 持续振荡触发、避免反复选同一无效子目标 | 草案 |
| 4 | `narrow_corridor_head_on_deadlock` | 走廊宽度、对向行人速度、初始横向偏置 | 对向相遇导致局部无解或相互等待 | freeze/deadlock 触发、后退或让位并恢复导航 | 草案 |
| 5 | `closing_gap_multi_pedestrian` | 两侧行人间距、闭合速度、到达相位 | 原可通行间隙被动态关闭，局部计划频繁失效 | 风险触发、等待/绕行/重新规划，而非硬闯 | 草案 |
| 6 | `lead_pedestrian_sudden_stop` | 前方距离、停止时刻、停止持续时间 | 前车式行人突然停下，跟随行为可能冻结 | freeze 触发、侧移或等待后回归原路径 | 草案 |
| 7 | `bottleneck_cross_flow_merge` | 瓶颈宽度、横穿流量、汇入时机 | 出口汇流时反复让行，可能超时或局部死锁 | 有界等待与 replan，避免无止境谦让 | 草案 |
| 8 | `goal_approach_lateral_interruption` | 目标附近横穿位置、速度、遮挡长度 | 接近目标时局部规划器反复改变方向或失败 | planner-failure / oscillation 后安全脱困并重新接近目标 | 草案 |

## 已获得的基础设施证据

1. 场景 1 的 train 单例已在 Arena 中运行：900 条遥测，终止为 `TIMEOUT`；
2. 场景 2 的 train 单例已在 Arena 中运行：485 条遥测，终止为 `COLLISION`；
3. 这两条结果仅说明情境可执行，且确实能产生基线困难；它们不是 PGRR 的效果证据。

详细运行记录见 `33_extension_runtime_smoke_result.md`。

## 下一步（不需要先训练）

1. 为 #3–#8 给出与 #1/#2 相同的 YAML 参数范围、地图几何和静态预览；
2. 用 scenario/seed 层面的配置审计器检查八类都只生成 train/validation；
3. 每类先运行一个 Base smoke，确认场景能启动并保存完整 outcome；
4. 在老师确认变量范围与比较对照后，冻结 protocol，再开始独立训练和验证。
