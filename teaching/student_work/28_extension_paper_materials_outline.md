# PGRR 扩展实验：论文素材骨架（不含结果）

更新日期：2026-09-04  
适用范围：拟议的独立 benchmark `pgrr_extension_v1`。  
边界：本文件是写作与记录模板，**不是实验结果**；不会修改当前论文、
`outputs/moderate/final/`、`moderate_v6` 或最终 checkpoint。

## 1. 一句话研究问题

在 Nav2 DWB 继续负责常态控制的前提下，PGRR 只在可观测的动态交互失败
持续出现时介入。独立的新场景要检验的是：这种“恢复后重接原目标”的设计，
是否在**斜向切入**和**遮挡后突现**中仍带来经验性的安全/完成收益；同时是否
付出时间、路径长度或运动平滑性代价。

这不是“证明绝对安全”或“所有指标均更优”的问题。

## 2. 可写入方法部分的素材

### 2.1 系统主线

```text
LiDAR / odometry / planner status
        -> failure trigger
        -> recovery state machine
        -> planning-guided action mask + DAgger policy
        -> temporary subgoal
        -> Nav2 DWB execution
        -> restore original goal / rejoin
```

- 常态：DWB 输出速度并导航；
- 触发：只在碰撞风险、冻结、振荡、死锁或规划失败等可观测证据持续时进入恢复；
- 恢复：高层选择临时子目标或 WAIT、BACKUP、REPLAN、CONTINUE；
- 执行与重接：仍由 DWB 执行临时目标，恢复完成后回到原目标；
- 安全监督：工程保护层；不得写成形式化安全保证。

图稿对应：作业三的“算法图”。训练中使用的特权信息必须以虚线支路表示，且
明确说明它不会进入部署时的观测。

### 2.2 新场景的变量表（待实现后填入具体范围）

| 场景族 | 交互机制 | 应记录的自变量 | 需要展示的示意要素 |
|---|---|---|---|
| `diagonal_cut_in_corridor` | 行人斜向切入前方 | cut side、angle、longitudinal phase、speed ratio、lateral offset、pedestrian count | 走廊、shelf、机器人起终点、三 waypoint 行人轨迹、切入点 |
| `occluded_side_emergence` | 行人从遮挡 gap 出现并横穿/斜穿 | occlusion length、gap location、first visible distance、phase、side、speed、density | shelf 遮挡屏、gap、初次可见位置、交叉点 |
| `turning_cross_flow`（可选） | 转向/汇流/交叉流 | turn direction、radius、merge point、flow imbalance、speed/phase | T/十字交叉、转向轨迹、汇流点 |

场景图的作用是“说明设置和变量”，不是展示有利结果。每张图都应写明随机种子
和密度如何影响该回合。

## 3. 实验协议素材

### 3.1 独立数据划分

每个 family-density cell 使用的 repeat 数：train/validation/test = 6/3/5。

```text
seed = B_split + 100 * family_index + 10 * density_index + repeat_index
train B = 91000
validation B = 93000
test B = 97000
```

必须保留完整 episode，且不同 split 之间不重叠：

- scenario identity；
- seed；
- 配置 JSON 的 SHA-256；
- 几何实现。

DAgger 的采样只能来自 train；模型和阈值只能根据 train/validation 决定。测试
仅在场景、代码、checkpoint 和统计方案冻结后运行。当前 `map_empty` runtime
下只可先做 train/validation 的编译与 smoke；不能把改写的 `map_id` 当作跨地图
泛化证据。

### 3.2 结果表的空模板

| 方法 | episodes | GOAL_REACHED | COLLISION | TIMEOUT | PLANNER_FAILURE | 时间 | 路径长度 | angular jerk |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Base (DWB) | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| Heuristic | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| Uniform BC | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |
| PGRR | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 |

填写前必须先保存原始 episode 行、manifest、配置 hash、checkpoint hash 与统计脚本
版本。配对比较以同一条件为单位；所有预设主比较应统一做多重比较校正。

## 4. 论文中可以逐步产出的内容

| 可立即产出 | 需等场景实现 | 需等训练/验证 | 需等最终测试 |
|---|---|---|---|
| 方法流程图、接口表、场景变量表、split/seed 表、运行记录模板 | 场景预览图、实际参数范围、smoke 日志摘要 | 训练/验证曲线、模型选择说明 | 数值主表、统计结果、失败轨迹分析 |

所有“待填”位置只能由新实验可追溯产物填充，不可从旧的 `moderate_v6` 发布结果
复制或推断。

## 5. 写作自查清单

- [ ] 说明 PGRR 是 failure-triggered recovery，而不是取代 DWB；
- [ ] 说明恢复动作受规划约束且会回到原目标；
- [ ] 区分训练特权信息与部署观测；
- [ ] 把安全监督表述为工程保护，不写成 formal guarantee；
- [ ] 报告效率和平滑性代价，不只报告成功率；
- [ ] 明确新 benchmark 与冻结 `moderate_v6` 的身份和证据边界；
- [ ] 每一个数字都有对应的原始 artifact 与脚本版本。
