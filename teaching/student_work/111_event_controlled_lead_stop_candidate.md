# 111 有限停顿后释放的领行人候选场景

## 本步实际完成了什么

生成了第一个可执行格式的 **train-only** 事件候选场景，用来替代旧版“领行人最终永久停在通道中央”的不可恢复设计。新场景仍然只用于开发筛选，不属于冻结测试集，也不是论文性能证据。

通俗地说：机器人在狭窄通道里追上一个走得较慢的行人；二者距离缩短到 3 m 时，行人停 3 s；随后行人继续前进，并从终点侧的开口离开机器人路线。这样 Base 仍可能因反应不佳而失败，但任务本身不再因为永久堵路而无解。

## 公平性与可行性检查

- 场景固定为 `train`，种子固定为 `92500`，没有生成 validation/test；
- Base 与 PGRR 使用同一个 JSON 和同一事件合同；
- actor 路线为非循环路线，不能重新回到通道中央；
- 初始人机距离为 `5.0 m`，大于 `3.25 m` 的触发重新武装边界；
- actor 最终位置到机器人直线路径的距离为 `3.441 m`；
- 事件映射通过 `ScenarioEventController` 严格解析；
- 场景 SHA-256 为 `f2db0efd56c0802ecf24597c808436279150773bede893234377a593d30b5657`。

## 验证结果

- Ruff：通过；
- 相关状态机、运行时适配和生成器测试：`17 passed`；
- JSON、预览图和 manifest 已实际生成；
- 尚未同步到 WSL、构建 ROS overlay 或运行 Gazebo，因此不能声称事件物理执行成功，更不能声称 PGRR 优于 Base。

## 工件

- `scripts/student/compile_event_controlled_lead_stop.py`
- `tests/unit/test_compile_event_controlled_lead_stop.py`
- `outputs/student/event_controlled_candidates/generated/arena/map_empty/lead_stop_bounded_release_v1_train_r00_s92500.json`
- `outputs/student/event_controlled_candidates/previews/lead_stop_bounded_release_v1_train_r00_s92500.png`
- `outputs/student/event_controlled_candidates/lead_stop_bounded_release_train_manifest.json`

## 下一道门

将默认关闭的事件控制源码与此候选同步到 WSL，构建三个 ROS 包，然后只跑这个固定种子的 Base/PGRR 单对冒烟。晋级条件是事件确实触发、3 s 后释放、场景仍可达，并且 PGRR 到达目标而 Base 发生动态行人相关失败；不满足时保留失败证据，先诊断，不换种子掩盖问题。
