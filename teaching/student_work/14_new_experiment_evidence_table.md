# 新增实验的证据与日志字段清单

目的：新场景开始前就确定“要保存什么”，避免实验结束后才发现无法做配对统计、失败分析或论文案例图。

## 每条 episode 必须保存

| 类别 | 字段 | 用途 |
|---|---|---|
| 可复现身份 | `episode_id`、`scenario_id`、`family`、`map_id`、`density`、`seed`、`replicate`、`method`、代码 commit、配置/场景 SHA256 | 找回同一条件，保证五种方法能配对 |
| 终点 | `outcome`、`terminal_reason`、实际 attempts | 区分 GOAL_REACHED / COLLISION / TIMEOUT / PLANNER_FAILURE / SIMULATOR_FAILURE / INVALID_RESET |
| 效率 | `duration_s`、`path_length_m`、`spl`、`mean_abs_angular_jerk_rad_s3` | 报告安全/完成收益的代价 |
| 任务几何 | 起点、目标、静态障碍参数、行人路线/速度/触发时刻 | 解释每一个新增场景到底改变了什么 |
| 恢复解释 | failure trigger 时间、trigger 类型/分数、动作 mask、选中动作 ID、临时目标、状态机状态、rejoin 时间 | 生成恢复时间线与失败案例 |
| 安全证据 | 最近距离、碰撞对象/原因、监督器是否覆盖命令 | 区分人-机器人、静态障碍、传感器歧义等失败 |

## 论文中可由这些字段生成的材料

| 论文材料 | 最小输入 |
|---|---|
| 终点结果表与配对统计 | 相同 condition key 下的 outcome、method |
| 效率/平滑性表 | 共同成功 pair 的 duration、path length、angular jerk |
| 场景示意图 | 场景 JSON 的障碍物、行人、起终点参数 |
| 匹配轨迹案例 | 同一 scenario/seed 下 Base 与 PGRR 的轨迹和 outcome |
| PGRR 恢复时间线 | trigger、mask、action、temporary goal、rejoin、terminal reason |
| 失败分析 | outcome、terminal reason、最近距离、触发和恢复日志 |

## 统计与表述边界

- 终点比较和连续指标比较应预先说明；不能在看完保留测试后临时挑一个最好看的指标。
- 只把 `SIMULATOR_FAILURE` 与 `INVALID_RESET` 作为基础设施问题处理；算法终点不能静默重跑或替换。
- `PLANNER_FAILURE` 是否进入推断性统计须在实验前确认；现有最终发布中它是描述性终点。
- 每一个“优于”结论都必须能反查至保留的 CSV、Parquet 或 JSON，而不是只靠截图。

## 当前状态

这是新场景实验的**日志设计草案**，不新增任何运行数据，也不修改已发布最终结果。

