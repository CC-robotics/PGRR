# PGRR extension v1：Arena/ROS smoke 运行前检查

日期：2026-09-04  
状态：场景 JSON 已准备；**Arena 容器启动被当前 WSL 的 Docker Integration 阻塞**。

## 已确认完成的运行前条件

- WSL 发行版：`Ubuntu-22.04`；
- 在线项目目录存在：`~/PGRR-online`；
- 新场景 JSON 带有运行脚本要求的 `scenario_id`、`seed`、`split`、`map_id`、`replicate`；
- 两个新场景族均通过 JSON schema、边界、静态 A* 和预览 smoke；
- 所有已生成条件都是 `train`，没有 held-out test。

## 当前阻塞现象

在 `Ubuntu-22.04` 中执行 Docker 检查时，Docker Desktop 返回：

```text
The command 'docker' could not be found in this WSL 2 distro.
We recommend to activate the WSL integration in Docker Desktop settings.
```

因此现在不能安全执行 `scripts/arena/run_baseline_episode.sh`。这不是场景或
PGRR 算法错误；启动前缺少 Docker Desktop 与这个 WSL 发行版的连接。

## 用户恢复后应做的最短操作

1. 打开 Docker Desktop；
2. 进入 **Settings → Resources → WSL Integration**；
3. 勾选 `Ubuntu-22.04`，然后点 **Apply & restart**；
4. 在 WSL 终端运行：

```bash
docker version
cd ~/PGRR-online
docker image inspect ramp-arena:humble >/dev/null && echo image-ready
```

当两条命令都成功后，才运行一个独立的、带唯一 episode ID 的新场景 smoke。

## 恢复后的安全 smoke 约束

- 只运行一个 `train` 场景；
- 使用唯一的 `RAMP_EPISODE_ID`，避免覆盖历史输出；
- 输出写入 `outputs/student/` 或其它独立学生目录；
- 只检查 reset、`/clock`、`/tf`、LiDAR、odom、日志和终止状态；
- 不训练、不选 checkpoint、不运行 held-out test、不生成论文结论。
