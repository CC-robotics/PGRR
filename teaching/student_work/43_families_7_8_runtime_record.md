# 第 7、8 类实际 Arena 运行回执

本轮通过 scripts/student/run_remaining_smokes.sh 顺序执行两个独立 train/Base 原型，模拟时限均为 90 s。

| 场景 | runner exit | outcome | samples |
|---|---:|---|---:|
| bottleneck_cross_flow_merge_medium_train_r00_s91610 | 1 | INVALID_RESET | 0 |
| goal_approach_lateral_interruption_low_train_r00_s91700 | 0 | COLLISION | 758 |

episode ID 分别为 student_v78_<scenario_id>_base。
原始 outcome 保存在 WSL /home/preface/PGRR-online/data/raw 下；独立控制台日志在 outputs/student/families_7_8_smoke，运行日志在 outputs/logs/baseline。

第 7 类 detail 为 NavigateToPose did not activate within the startup deadline。
清理前日志出现 /tf_static 的 DURABILITY_QOS_POLICY 警告，但尚不能确定因果关系。该次失败完整保留，不能解释为 Base 导航失败或 PGRR 的优势。

第 8 类 detail 为 privileged robot-human overlap；physical_goal_distance_m=3.177080457970749。
它证明该空间原型在目标附近产生了实际碰撞终止，不证明精确一次性触发机制或 PGRR 效果。

本轮还确认：外层 run_baseline_episode.sh 不转发 RAMP_BASELINE_RUNTIME_LOG / STATUS_LOG，实际日志使用内部默认路径。之前“日志必然随容器消失”的推断不准确。

下一项为第 7 类初始化诊断，保留本次 INVALID_RESET。必要时使用新 episode ID 复查，不替换该失败记录。
