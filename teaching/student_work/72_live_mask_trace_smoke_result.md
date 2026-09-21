# 72. Train-only 上游掩码轨迹真实运行结果

## 这一步回答什么

这次工作只验证一件事：默认关闭的三层掩码诊断在显式开启后，能否在真实
Arena/ROS 训练场景中完整记录，而不把一次开发 smoke 包装成性能实验。

使用场景为 `lead_pedestrian_sudden_stop_low_train_r00_s91500`，split 为
`train`，策略入口为 PGRR，超时为 90 秒。没有读取或改写冻结的
`moderate_v6`、最终 checkpoint 或 `outputs/moderate/final`。

## 真实执行过程

ROS overlay 构建成功，`ramp_msgs`、`ramp_ros`、`ramp_bringup` 三个包完成。
两次失败尝试均按完整 outcome 保留，没有删除或替换：

1. 原始 episode ID 以 `20260912` 结尾，结果为 `COLLISION`、434 个样本。
   WSL 同步时错误的换行转换截断了类名，恢复管理器发生 ImportError。
2. `retry01` 结果为 `COLLISION`、442 个样本。启动器把 `1` 作为整数传给
   ROS 的 bool 参数，引发 `InvalidParameterTypeException`。

修复同步方式并把环境变量显式转换为 ROS 的 `true/false` 后，`retry02`
完整走完 episode wrapper：

- episode：`pgrr_extension_mask_trace_leadstop_train_r00_pgrr_20260912_retry02`
- outcome：`TIMEOUT`
- detail：`configured episode timeout`
- 遥测样本：896，与 outcome 中的 sample count 一致
- 含三层轨迹的决策行：110
- `map_connectivity`：110 次
- `observable_scan`：110 次
- `path_corridor`：110 次
- 顺序完整的决策行：110；缺层或错序：0
- 轨迹行中的动作：WAIT 50、BACKUP 55、REPLAN 5
- 掩码追踪、ROS 接入、启动预检与校验器相关回归：29 passed
- Ruff 与 `git diff --check`：通过（仅报告既有 CRLF 提示）

运行日志的两处 traceback 都发生在 episode 结束后，来自
`world_generator` 的 `ExternalShutdownException` 与重复 shutdown；未发现
ImportError、参数类型错误或 recovery manager 进程死亡。

机器可读校验结果见
`outputs/student/eight_family_pilot/mask_trace_smoke_retry02_validation.json`。
校验器为 `scripts/student/validate_mask_trace_smoke.py`。

曾尝试运行全部 780 项单元测试；首个非相关失败来自本机离线环境找不到
`ffmpeg`，发生在最终制品清单的视频夹具中。因此这里不声称全仓 780 项通过，
只报告与本次改动直接相关且已完整执行的 29 项回归。

## 能说和不能说的结论

可以说：三层诊断已在真实 Arena train-only 回合中完整落盘，顺序与样本数
通过自动校验；此前的遥测盲区已经可以在未来非冻结开发回合中直接观察。

不能说：这次 PGRR 导航成功，或 PGRR 优于 Base。该回合真实结果是
TIMEOUT，且这里只运行了一个 PGRR 开发回合，没有形成配对性能比较。

## 下一步

这 110 个决策的只读分层统计已经完成，结果见材料 73：85 次首次在 LiDAR
层清空，25 次首次在路径走廊层清空。下一步保持算法阈值和最终模型不变，
先在少量新的 train/validation 回合复核该现象，再决定是否值得做受控消融。
