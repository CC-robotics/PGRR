# 第 2 讲：A*、DWA/DWB 与恢复子目标

## 全局路径与局部控制

A* 在离散占据栅格上寻找全局路径；DWA/DWB 在短时间窗口内采样速度并评价轨迹。
PGRR 不用网络持续输出速度，而是选择一个短程子目标，仍由经典局部规划器执行。
这保留了经典控制接口，也让恢复动作可解释。

## 8 邻接 A*

格点 `(row, column)` 有 4 个直邻居和 4 个斜邻居。直移代价 1，斜移代价
`sqrt(2)`。octile heuristic 为：

```text
h = max(dx, dy) + (sqrt(2) - 1) * min(dx, dy)
```

它对 8 邻接移动可采纳。斜向移动还必须检查相邻两个直角格都为空，否则路径会穿过
障碍尖角。确定性要求优先队列使用递增序号解决相同优先级。

Assignment 1 的边界条件：起终点占据、无路径、起点等于终点、窄门、相同代价路径。

## 25 个恢复动作

21 个子目标由半径 `0.6/1.0/1.4 m` 和角度
`-90/-60/-30/0/30/60/90 deg` 的笛卡尔积构成，ID 按半径优先固定为 0--20。
WAIT、BACKUP、REPLAN、CONTINUE 固定为 21--24。

机器人坐标系下：

```text
p_r = [r cos(theta), r sin(theta)]
p_w = R(yaw) p_r + [x_robot, y_robot]
```

非子目标动作必须返回 `None`。目标 yaw 指向该子目标方向。

## Action mask

策略前必须排除占据、越界、局部不可达、无连通自由空间、行人占据、后方不安全和
不可用 REPLAN。mask 是规划约束，不是训练标签。即使网络对非法动作给出最高原始
logit，也必须在 argmax/softmax 前屏蔽。

## 与 DWB 的关系

DWB 负责从当前姿态跟踪临时子目标，PGRR 只在 2 Hz 左右作高层选择。控制仍可在
10 Hz 更新。子目标保持、恢复超时和重接原路径由状态机处理，不能每帧左右重选。

## 验收建议

```bash
pytest tests/unit/test_astar.py tests/unit/test_action_space.py \
  tests/unit/test_action_mask.py tests/student/test_student_tasks.py -q
```

生成一张栅格图：障碍、搜索路径、机器人姿态和 21 个候选点。解释一个被 mask 的
动作为何非法。
