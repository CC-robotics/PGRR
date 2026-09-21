# 作业四准备：新增场景的配置字段检查清单

日期：2026-08-28  
状态：设计与审查清单；不生成场景，不启动训练/评测，不修改 `moderate_v6`。

## 1. 使用范围

本清单用于未来创建**独立的新实验 benchmark**。它借鉴
`configs/experiments/scenario_catalog_moderate_v6.yaml` 的可复现字段，
但不能复制其测试 split 或写入其输出目录。

在教授确认研究问题前，新增场景只可保留为草案。推荐的候选族见
`08_new_scenario_parameter_draft.md`，划分原则见
`11_independent_experiment_split_template.yaml`。

## 2. 每个 benchmark 顶层必须明确的字段

| 字段 | 为什么需要 | 审查问题 |
|---|---|---|
| `benchmark_id` | 与发布 benchmark 隔离 | 是否是新的名称，且不是 `moderate_social_navigation_v6`？ |
| `schema_version` | 记录配置格式 | 后续脚本能否识别此版本？ |
| `map.id` 与 `bounds_m` | 决定可用空间与地图版本 | 地图是否已固定并有版本/哈希？ |
| `robot.radius_m` | 决定静态和动态安全间距 | 是否与原比较方法使用同一机器人？ |
| `actor_dynamics_version` | 行人代理行为也属于实验条件 | 行人路线/更新频率是否被明确记录？ |
| `densities` | 难度可重复 | 低、中、高分别是多少人，而不是模糊描述？ |
| `splits` | 防止训练看见测试 | 是否按 `scenario_id + seed` 而不是按帧切分？ |
| `output` | 保留溯源 | 是否写到独立目录，绝不写 `outputs/moderate/final`？ |

## 3. 每个场景族必须填写的字段

| 字段 | 示例含义 | 检查点 |
|---|---|---|
| `id` | `narrow_corridor_opposing_flow` | 稳定、语义明确、不会与已有场景混名。 |
| `layout` | 窄走廊 / T 路口 / 门口 | 编译器或场景生成器实际支持；否则先登记实现任务。 |
| `robot_start` / `robot_goal` | 机器人任务 | 起终点都在自由空间内，朝向单位为弧度。 |
| 静态几何参数 | 走廊宽度、门宽、遮挡物尺寸/位置 | 不与机器人半径、膨胀安全间距冲突。 |
| 行人参数 | 人数、半径、路线、速度、起始时间偏移 | 每个行人能由 seed 唯一复现。 |
| 难度变量 | 如宽度/速度/触发距离 | 每次只改变预先声明的变量；其余保持固定。 |
| 终止与超时 | 成功阈值、碰撞、时限 | 必须与对比方法共享，不能为某一方法单独放宽。 |

## 4. 编译前的“纸面”检查

1. **可通行性**：机器人半径、地图障碍、行人圆柱和安全余量后，仍存在合理通道；不要把“无路可走”误当成算法困难。
2. **时间相遇性**：根据机器人预计到达时间与行人路线检查，交互确实会发生；不能让行人已经离开交叉点。
3. **可观测性边界**：部署策略只能使用 LiDAR、路径、目标、速度、规划状态和历史；新增场景不能把行人真值送入 BC/PGRR 推理输入。
4. **方法公平性**：Base、Standard、Heuristic、Uniform BC、PGRR 使用相同 `condition_key`、地图、起终点、行人轨迹和 seed。
5. **数据隔离**：同一 `scenario_id + seed` 只能属于 train、validation、held-out test 之一。
6. **溯源字段**：场景 JSON/YAML、配置、代码提交、生成 manifest 都要有 SHA256 或固定版本记录。

## 5. 冒烟阶段和正式阶段应分开

| 阶段 | 可做什么 | 不可宣称什么 |
|---|---|---|
| 纸面设计 | 参数表、碰撞余量计算、split 草案 | 算法提升或论文结论 |
| 少量冒烟 | 检查复位、话题、日志、交互是否发生 | 正式成功率/显著性 |
| 校准 | 确认 Base 难度合理、冻结参数 | 继续根据 test 调阈值 |
| 正式保留测试 | 在配置锁定后一次性 paired evaluation | 可用来回调训练或改阈值 |

## 6. 最小 manifest 记录建议

每一条实际运行条件至少应记录：

```text
benchmark_id, scenario_id, family, map_id, density,
seed, replicate, condition_key, robot_start_goal,
static_obstacle_parameters, actor_route_parameters,
actor_speed_parameters, config_sha256, scenario_sha256,
method, terminal_outcome
```

终止类别必须保留 `GOAL_REACHED`、`COLLISION`、`TIMEOUT`、
`PLANNER_FAILURE`、`SIMULATOR_FAILURE` 与 `INVALID_RESET`，不能因结果不理想而删除或重试算法结果。

## 7. 教授确认前的结论

我们已能把新场景做成“参数可检查、条件可配对、数据可隔离”的实验计划；但新地图、场景族优先级、正式重复次数、统计终点和是否重新训练，均应由教授确认后再写入实际配置。
