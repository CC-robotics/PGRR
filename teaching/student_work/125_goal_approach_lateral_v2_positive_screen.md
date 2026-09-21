# 目标附近横向干扰 v2 单seed正向筛选

## 优化内容

这是用户指定四个第一优先级场景中的第2个。优化版没有修改PGRR模型或阈值：

- 机器人路线由原22 m缩短为15 m；
- 横穿点设在`x=15`，其后保留5 m原目标验证段；
- 删除全部静态墙，避免Base失败被静态几何混杂；
- 行人先在路线外等待，机器人进入中段后只横穿一次；
- 事件持续5 s后将行人固定在距中心线1.35 m的路线外终点；
- seed固定为`97100`，不做seed搜索。

离线9/9检查通过。标称交互时刻38.46 s；真实PGRR恢复在40.43 s开始，符合希望
把原来约81.65 s的过晚交互前移至实验中段的设计目标。

## 真实配对

首次Base启动因必需topic不全产生0样本`SIMULATOR_FAILURE`，证据已保留。唯一一次
同seed重试得到有效Base结果：

| 方法 | outcome | 样本数 | 物理目标距离 |
|---|---|---:|---:|
| Base（retry01） | `COLLISION`，动态人机重叠 | 419 | 5.170 m |
| PGRR | `GOAL_REACHED` | 663 | 0.239 m |

PGRR事件在38.36 s触发、43.86 s释放；恢复状态依次经过`EMERGENCY_STOP`、
`PENDING_RECOVERY`、`RECOVERY`、`REJOIN`并于44.42 s恢复`NORMAL`和原目标。决策包含
WAIT 2次、BACKUP 1次、CONTINUE 5次。

## 当前资格

该场景通过单seed筛选，允许进入预声明的3-seed train复现，但尚未完成train复现或
独立validation：

- 四个第一优先级场景：1个已独立验证，1个单seed正向，2个待优化；
- 八场景正式进度仍为`1/8`；
- 本结果尚不能写作已验证论文场景。

机器可读汇总：
`outputs/student/goal_approach_lateral_v2_screen/screen_summary.json`。

