# 93. Observation shadow 构建环境阻塞诊断

## 已执行检查

WSL 五个源码达到 5/5 后，实际执行了 `make -C /home/preface/PGRR-online build`。构建脚本在进入 ROS 编译之前退出，报告 Arena image 缺失。随后在同一 `Ubuntu-22.04` 发行版中只读执行 Docker 镜像/容器查询，系统明确报告 `docker` 命令不可用，并要求在 Docker Desktop 中启用 WSL integration。

尝试通过 Windows 应用控制启动 Docker Desktop 时，应用启动批准超时；因此没有擅自改变 Docker Desktop 设置。

## 当前状态

- WSL 运行源码：5/5 哈希匹配，证据在 `outputs/student/refactor_baseline/observation_shadow_wsl_source_check.json`。
- ROS overlay：未开始构建。
- Arena image：当前 WSL 不可见，不能判断本地镜像是否仍在 Docker Desktop 中。
- Arena smoke：未启动。
- 冻结证据、checkpoint、阈值：未改动。

机器可读阻塞记录：`outputs/student/refactor_baseline/observation_shadow_build_blocker.json`。

## 恢复条件

用户回到电脑后启动 Docker Desktop，并确保 `Ubuntu-22.04` 的 WSL integration 已开启。只需先在 WSL 执行 `docker version`；若同时出现 Client 和 Server，再重试 `make build`。在此之前可以继续做不依赖 Arena 的作业二测试设计和作业三/论文整理。
