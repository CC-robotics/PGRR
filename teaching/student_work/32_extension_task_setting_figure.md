# PGRR extension v1：任务设置示意图草稿

图文件：`outputs/student/extension_paper_materials/pgrr_extension_v1_task_settings.png`  
状态：基于 smoke 预览的设置图草稿；不含任何算法结果。

## 图的用途

这张图用于作业三和未来扩展论文的 **Task settings / Scenario design** 部分，帮助读者
直观看到两类独立动态交互：

1. `diagonal_cut_in_corridor`：行人斜向切入机器人前进走廊；
2. `occluded_side_emergence`：行人从 shelf 遮挡侧出现，再横穿通道。

图中的蓝线是仅考虑静态障碍时的 A* 路径，绿色圆点与红色星号分别是机器人起点和
目标，橙色箭头是行人预定 one-shot 路线。它们描述**设置**，不描述导航结果。

## 英文图注草案

> **Preliminary task-setting smoke previews for the independent
> `pgrr_extension_v1` benchmark.** (A) A pedestrian diagonally cuts into a
> shelf-bounded corridor. (B) A pedestrian emerges from the side of a shelf
> occluder and crosses the corridor. Blue paths show static A* reachability
> only; the panels report no navigation or safety outcomes.

## 使用边界

- 可用于课程汇报和实验设置草稿；
- 不能作为 Gazebo 截图、真实轨迹或任何方法优劣证据；
- 正式论文使用前，应等 Arena/ROS smoke 通过并冻结场景参数后重新导出。
