# Validation selector 路径真实复现

## 本步做了什么

运行了材料 76 已静态预检的单个非冻结开发场景：

- 场景：`lead_pedestrian_sudden_stop_low_validation_r00_s93500`
- split / seed：`validation` / `93500`
- episode：`pgrr_masktrace_leadstop_validation_r00_20260912`
- 策略入口：PGRR
- 超时：90 秒
- 上游三层 mask trace：显式开启

运行前确认 Docker Engine 与 `ramp-arena:humble` 镜像可用，episode ID 未被
占用，并按忽略 CRLF 后的 SHA-256 确认 WSL 中两个启动器和恢复节点与当前
Windows 工作区内容一致。只同步了预检场景，没有接触冻结测试集、最终模型、
阈值或 `outputs/moderate/final`。

## 真实结果

episode wrapper 完整结束，但导航结果为 `TIMEOUT`，不是成功：

- telemetry：898 行，与 outcome 中的 sample count 一致；
- selector 决策：191 次；
- 三层 trace 完整且顺序正确：191/191；
- malformed trace：0；
- map/connectivity 首次清空临时子目标：0 次；
- observable scan 首次清空：172 次；
- path corridor 首次清空：4 次；
- 三层之后仍保留临时子目标：15 次；
- 动作：WAIT 31、BACKUP 141、REPLAN 19；
- runtime 中没有 ImportError、ROS 参数类型错误或 recovery manager 进程死亡；
- 两个 traceback 均为已知 Arena shutdown 清理异常。

机器可读校验结果为
`outputs/student/eight_family_pilot/mask_trace_leadstop_validation_runtime_validation.json`。
六回合汇总现在包含 350 次完整 selector trace，其中 train 159 次、validation
191 次。

## 可以说什么

可以说：同族 train/validation 开发场景都真实进入了恢复选择流程，三层 mask
诊断链路首次完成跨 split 复现；LiDAR 层在 validation 回合也最常首次清空临时
子目标。

不能说：PGRR 在 validation 导航成功、PGRR 优于其他方法、该场景属于冻结测试，
或者三层 mask 导致了 TIMEOUT。这里只有一个非冻结 validation 开发回合，而且
其真实 outcome 是 TIMEOUT。

## 对作业二和作业三的意义

- 作业二：证明当前恢复节点的 selector/mask 接缝能在 train 与 validation 的真实
  ROS 回合中被同一诊断工具观测，为以后默认关闭的 shadow wiring 提供运行证据。
- 作业三/论文：可以把“跨 split 诊断路径复现”写入开发过程或方法验证，但不能把
  这一个回合写成性能结论；论文主结果仍只来自冻结最终证据。
