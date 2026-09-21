# 109 事件控制 ROS 接线前检查

## 本步实际执行了什么

对事件控制进入 ROS/Arena 前所依赖的五个源码边界进行了只读检查，并将当前已有前提、尚缺接线和接线后的验收条件写入可复现 JSON 报告。本步没有启动 ROS、Gazebo 或 Arena，也没有修改任何算法阈值、策略模型或冻结证据。

## 结果

- 事件状态机、契约适配器、actor controller 入口、实际机器人位姿、路线时钟和任务 reset 回调等前提为 `7/7`；
- 实际运行接线为 `0/6`，符合“尚未接 ROS”的预期；
- 已明确 7 个最小接线步骤：仅在新 train/validation 场景写入事件配置、默认关闭参数、reset 清理、位姿新鲜度门禁、转移日志、episode logger 记录和启动器显式开关；
- 已固定接线前五个源码文件的 SHA-256，便于接线后证明默认关闭路径没有被悄悄改变；
- 前检及事件契约相关测试共 19 项通过。

## 解释

`0/6` 不是测试失败，而是本次检查确认当前仓库仍停在“离线状态机已经完成、ROS 运行时尚未接入”的安全边界。现在可以按报告列出的顺序实施默认关闭接线，但不能宣称事件场景已经可执行。

## 下一步

先实现最小默认关闭接线和纯测试替身验证：开关未设置时保持旧行为；开关开启时能够构造状态机、在 task reset 时清空状态，并记录一次激活和一次释放。通过后再同步 WSL、构建 overlay 和运行非冻结 train-only 冒烟测试。

## 工件

- `scripts/student/preflight_event_control_ros_wiring.py`
- `tests/unit/test_preflight_event_control_ros_wiring.py`
- `outputs/student/anchor_feasibility/event_control_ros_wiring_preflight.json`

