# 第 7、8 类实际行人运动核验

日期：2026-09-09。范围：读取已保存 episode JSONL 中的 simulator-truth `privileged.human_positions`，不作为策略输入，不修改任何实验结果。

可复现命令由 `scripts/student/analyze_privileged_actor_motion.py` 提供。该脚本汇总每个行人的坐标范围、路径长度和主轴换向次数。

## 第 7 类：瓶颈横向汇入

episode：`student_v78_bottleneck_cross_flow_merge_medium_train_r00_s91610_base_retry01`

- 431 个样本，0–41.7915 s，outcome 为 COLLISION。
- actor 0 的 x 始终为 15.0 m，y 为 11.500–12.493 m，沿 y 轴换向 18 次。
- actor 1 的 x 始终为 16.5 m，y 为 11.509–12.500 m，沿 y 轴换向 26 次。
- 全回合有限的最小 robot-human distance 为 0.624113 m。

结论：两名行人在瓶颈区域进行了真实的横向往返运动，几何机制与“瓶颈横向交汇”基本一致。此次 Base 碰撞只能证明该单次原型产生了冲突，不能证明统计优势。

## 第 8 类：目标附近侧向干扰

episode：`student_v78_goal_approach_lateral_interruption_low_train_r00_s91700_base`

- 758 个样本，0–83.25 s，outcome 为 COLLISION。
- 单名 actor 的 x 始终为 24.0 m，y 为 11.100–12.796 m，沿 y 轴换向 20 次。
- 全回合有限的最小 robot-human distance 为 0.705903 m。

结论：目标附近确有持续的侧向横穿干扰，但当前实现是循环空间原型。它不是“一次性突然介入”，也没有实现根据机器人接近目标的事件触发。后续材料必须使用“目标附近持续横穿”这一准确描述，除非另行实现并验证事件触发版本。

## 诊断边界

`human_positions` 是评测/诊断真值，不得进入 PGRR 测试观测。换向计数受采样、避让和数值抖动影响，用于确认运动发生及其大致模式，不应被当作方法性能指标。
