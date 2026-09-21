# 112 有限停顿领行人场景的首次真实运行门

## 本步实际完成了什么

将事件控制源码和固定种子 `92500` 的 train-only 场景安全同步到 WSL，原有运行文件备份到独立目录；9/9 文件同步哈希一致。随后在 Arena Docker 中重建 ROS overlay，`ramp_msgs`、`ramp_ros`、`ramp_bringup` 共 3/3 包构建成功。

同一 JSON 先后用于 Base 和 PGRR，不改种子、不改算法阈值。

## 真实结果

### Base：有效 episode

- 结果：`TIMEOUT`，868 samples；
- 最终物理目标距离：`0.931 m`；
- 事件在仿真时间 `80.0199 s` 激活；
- 在 `83.5164 s` 释放；
- outcome 中完整记录了 `pre_event_to_active_event` 和 `active_event_to_released`。

这证明新增事件控制在真实 Gazebo/Base 运行中能够触发并释放。但触发过晚，留给机器人完成任务的时间不足，因此当前几何/时序仍不适合作为最终对照场景。

### PGRR：没有形成有效配对

第一次 PGRR 运行在事件触发前结束为 `SIMULATOR_FAILURE`：只有 163 samples，机器人距目标仍为 `18.136 m`，`scenario_events=[]`。同场景同种子的唯一一次 retry 又在启动阶段等待必需 `/ramp/*` 话题超时，没有形成 outcome。两次都不是可用于比较的方法结果。

因此本场景当前结论是 **运行门未决**，不是“PGRR 失败”，也不是“Base 优于 PGRR”。禁止晋级为八个论文案例。

## 验证与证据

- 同步脚本和运行汇总脚本 Ruff 通过；
- 两项新单元测试通过；
- Base/PGRR outcome、三份运行日志、同步清单和哈希汇总已经复制回项目；
- 汇总明确设置 `paired_method_claim_authorized=false` 和 `core_case_promotion_authorized=false`。

## 下一道门

先运行一个历史上已稳定完成的、非冻结 train-only PGRR 控制场景，判断 `/ramp/*` 启动失败和 PGRR 仿真减速是全局运行环境问题还是仅此候选的问题。控制场景若也无效，先修运行环境；控制场景有效，才把该候选的触发位置前移并重新进行一次固定配对。不能继续用重复重跑代替诊断。

## 工件

- `scripts/student/sync_event_control_candidate.py`
- `scripts/student/summarize_event_lead_stop_runtime.py`
- `outputs/student/event_controlled_candidates/runtime_s92500/runtime_gate_summary.json`
- `outputs/student/event_controlled_candidates/runtime_s92500/`
