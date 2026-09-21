# 106 事件可控锚点配置契约

## 本步实际执行了什么

为“前方行人突然停止”和“接近目标时侧向打断”建立了独立的、尚不可执行的 train/validation 配置契约，并编写校验器。契约先固定实验语义和验收条件，避免直接修改运行控制器后才发现比较不公平或事件仍未释放。

## 契约内容

- 只允许 train 和 validation，不生成 test；
- 每种方法使用相同事件契约和配对 seed；
- 事件控制器可以读取仿真状态来触发场景，但该状态绝不进入策略观察；
- 每次事件必须依次出现 `pre_event`、`active_event`、`released`，且只触发一次；
- 必须记录触发、持续时间和释放；释放后行人必须离开机器人中心路线；
- 必须先证明释放后仍存在无碰撞任务路线；
- “突然停止”使用有限时长停车后继续移动，禁止永久停在中心线；
- “目标附近打断”使用接近目标后的一次性横穿，禁止提前开始的循环横穿；
- 当前不启用遮挡贡献声明。

## 验证结果

配置校验通过，两个 variant、四个 train/validation seed 均符合边界。4 项单元测试覆盖正常配置、禁止 test、禁止中心线阻塞释放和禁止重复 seed。

## 边界

本步没有生成可执行场景，也没有声称现有 actor controller 已支持这些事件。下一步是先在核心 Python 中实现并单测独立事件状态机，确认它不会泄漏到策略输入，再考虑 ROS 运行接线。

## 工件

- `configs/experiments/pgrr_event_controlled_anchor_contract_v1.yaml`
- `scripts/student/validate_event_controlled_anchor_contract.py`
- `outputs/student/anchor_feasibility/event_controlled_anchor_contract_validation.json`
