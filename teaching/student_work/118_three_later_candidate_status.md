# 后续三个新候选场景的实际状态

这三个候选与从冻结正式结果中筛出的八条 episode 例子无关；它们属于独立的 train/validation-only 场景扩展开发，并且只有通过场景级重复验证后才可能计入教授要求的八个场景。

| 候选 | 当前阶段 | 已有文件 | 运行结果 | 是否合格 |
|---|---|---|---|---|
| 有限停车后释放的领行人 | 已生成并实跑 v1/v2 | `outputs/student/event_controlled_candidates/generated/arena/map_empty/lead_stop_bounded_release_v{1,2}_train_r00_s92500.json` | v2 Base=COLLISION，PGRR=PLANNER_FAILURE；Base 碰撞含静态几何干扰 | 否 |
| 接近目标后一次性侧向横穿 | 只完成事件契约和离线状态机适配 | `configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml` 中 `goal_approach_one_shot_crossing_v1` | 尚未生成 Arena JSON，尚未实跑 | 未完成判断 |
| 开放空间双行人收口后释放 | 已生成并实跑 | `outputs/student/event_controlled_candidates/generated/arena/map_empty/closing_gap_open_release_v1_train_r00_s91410.json` | Base=TIMEOUT，PGRR=TIMEOUT；两侧事件均完整触发与释放 | 否 |

因此目前不能说“三个新场景已经确认合格”。准确状态是：两个负结果已经完整保存，一个仍停留在可执行场景之前。三者都没有进入冻结正式论文结果，也没有修改最终 checkpoint、测试集或算法阈值。
