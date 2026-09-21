# 71. 三层遥测 smoke 运行前检查

更新日期：2026-09-12

## 已执行

新增并运行 `scripts/student/preflight_mask_trace_smoke.py`，针对已有的
`lead_pedestrian_sudden_stop_low_train_r00_s91500` 场景检查：

- 场景位于项目内部，且 metadata 明确为 `train`；
- 场景路径、episode ID 均不包含冻结标记；
- 新 episode ID 在当前 Windows 工作区不存在，不会覆盖已有结果；
- ROS 参数默认关闭；
- 外层和容器内启动脚本均能传递显式的遥测开关；
- 策略固定为 PGRR，单回合超时为 90 秒。

预检结果为 `ready=true`，结构化记录保存在
`outputs/student/eight_family_pilot/mask_trace_smoke_preflight.json`。工具的三项
单元测试覆盖正常 train 场景、拒绝非 train split 和拒绝覆盖已有 episode。

## 当时运行阻塞（已解决）

实际 Arena 回合尚未启动。检查时，WSL 的 `/home/preface/PGRR-online` 尚未包含
本次新增代码和目标场景，并且 WSL 明确报告 Docker 命令不可用、需要恢复 Docker
Desktop 的 WSL 集成。Windows 侧也未发现正在运行的 Docker 进程或可调用的 Docker
CLI。由于运行容器是必要条件，不能把预检通过写成 simulator smoke 通过。

随后 Docker/WSL integration 已恢复，所需文件已按清单同步，ROS overlay 构建
成功。真实运行、失败重试保留情况与最终校验结果见材料 72；分层统计见材料 73。

## 环境恢复后已执行的动作

先启动 Docker Desktop 并确认 Ubuntu-22.04 的 WSL integration 可用；随后同步本次
明确列出的代码、脚本和 train-only 场景到 WSL 工作镜像，再使用预检生成的新
episode ID 执行一次。运行后只解析 `mask_stage=map_connectivity`、
`mask_stage=observable_scan`、`mask_stage=path_corridor` 是否存在和顺序是否正确。
不据此修改安全阈值，也不接触冻结证据。
