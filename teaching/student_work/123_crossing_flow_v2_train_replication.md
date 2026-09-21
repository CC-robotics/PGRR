# Crossing-flow v2 训练内复现门结果

## 固定协议

- 场景族：`crossing_flow_medium_anchor_v2`；
- 路线：15 m，最后冲突点后保留6 m重新加入路段；
- 时限：90 s；方法：Base、PGRR；
- 预声明train seeds：`95010`、`95011`、`95012`；
- 晋级门：3个同协议配对中至少2个满足Base未到达且PGRR到达；
- 三次重复之间不改几何、时限、checkpoint或算法阈值，不替换seed。

对应预声明文件为
`configs/experiments/pgrr_advantage_screen_crossing_v2_replication_plan.yaml`。

## 真实运行结果

| 重复 | seed | Base | Base样本 | PGRR | PGRR样本 | 正向配对 |
|---:|---:|---|---:|---|---:|---|
| r00 | 95010 | `COLLISION` | 271 | `GOAL_REACHED` | 757 | 是 |
| r01 | 95011 | `COLLISION` | 408 | `GOAL_REACHED` | 805 | 是 |
| r02 | 95012 | `COLLISION` | 264 | `GOAL_REACHED` | 710 | 是 |

结果是3/3正向配对，高于预声明的2/3门槛。三次Base失败均记录为
`privileged robot-human overlap`，不是静态墙碰撞；三次PGRR最终物理终点误差分别为
0.206 m、0.241 m和0.239 m。

三次PGRR轨迹均记录到恢复状态并重新返回`NORMAL`：

- r00：`NORMAL -> RECOVERY -> EMERGENCY_STOP -> RECOVERY -> REJOIN -> NORMAL`；
- r01：包含两轮恢复/重新加入，并记录2次原目标恢复；
- r02：`NORMAL -> EMERGENCY_STOP -> PENDING_RECOVERY -> RECOVERY -> REJOIN -> NORMAL`。

r00使用2次临时子目标决策；r01/r02没有选择临时子目标，但使用了WAIT、BACKUP和
CONTINUE恢复动作。因此这组证据支持“失败触发恢复后重新加入原任务”，但不支持
“每次成功都必须依赖临时子目标”的额外说法。

## 基础设施异常的保留方式

r02第一次PGRR启动在0样本处得到`INVALID_RESET`，原因是NavigateToPose未在启动
截止时间内激活。该无效尝试没有被删除；脚本先验证并复制原始证据，然后只允许同
场景、同seed、同方法重试一次。重试得到表中710样本的有效`GOAL_REACHED`。

这不是“替换失败episode”：`INVALID_RESET`是按结果枚举保留的基础设施无效运行，
不进入性能配对；其原始sidecars与唯一重试证据都位于
`outputs/student/advantage_scenario_screen_v2_replication/runtime/`。

## 当前研究资格

该场景已从“单seed正向候选”晋级为**训练内可复现候选**：

- 训练内可复现候选：`1/8`；
- 完成独立validation的新场景：`0/8`；
- 论文新场景结论：尚未授权。

下一步必须先冻结独立validation的seed和判定规则，再运行未用于设计的配对。不能
根据validation结果继续调整本场景，不能与冻结`moderate_v6`测试合并，也不能将
3/3训练结果表述为一般性优越性。

机器可读报告与恢复摘要：
`outputs/student/advantage_scenario_screen_v2_replication/replication_summary.json`。

