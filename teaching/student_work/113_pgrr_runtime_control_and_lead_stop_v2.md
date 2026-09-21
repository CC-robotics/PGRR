# 113 PGRR 运行健康对照与领行人 v2 配对

## 先验证 PGRR 运行链

使用历史上曾完整运行的非冻结 train-only 斜向切入场景（种子 `91000`）做环境控制。当前 PGRR 再次形成有效 episode：`TIMEOUT`、893 samples、最终物理目标距离 `0.764 m`。这说明 PGRR、模型加载、ROS/Docker 主运行链总体可用；上一轮新候选的无效 episode 不能归因于全局环境瘫痪。

## 领行人 v2 做了什么

保留 v1 全部工件，新建同种子 `92500` 的 v2：行人初始距离从 `5.0 m` 缩短到 `3.75 m`，速度由 `0.20 m/s` 降到 `0.10 m/s`，只为让一次 3 s 停顿较早发生。没有修改 PGRR 模型、恢复阈值或冻结数据。

v2 继续满足：train-only、Base/PGRR 共用同一 SHA-256 为 `0a446acbdb6dd34bcc93d188573549ed0b8cc05ba8083240ab1d881cbe9bb624` 的 JSON、非循环 actor、固定种子和一次激活/一次释放。

## 真实配对结果

| 方法 | 结果 | 样本 | 最终物理目标距离 | 事件激活 / 释放 |
|---|---|---:|---:|---:|
| Base | `COLLISION` | 220 | 16.892 m | 34.532 / 38.029 s |
| PGRR | `PLANNER_FAILURE` | 873 | 15.509 m | 32.001 / 35.032 s |

PGRR 的终止原因是 `recovery_sequence_timeout`。两种方法都完整记录了事件激活和释放，因此这是一对有效的开发比较；但它不满足“Base 因动态行人失败、PGRR 到达目标”的核心晋级条件。

更重要的是，Base outcome 把碰撞归因为“机器人 footprint 与已知静态场景几何相交”，不是动态行人碰撞。这说明当前狭窄货架几何混入了静态碰撞机制，不能用来证明 PGRR 对领行人停顿的优势。

## 决定

v2 不晋级，也不继续通过改种子或微调阈值抢救。保留它作为“事件控制有效但机制不纯、PGRR安全未完成”的负结果。下一候选转向多行人 closing-gap，并优先去除会产生静态碰撞归因的窄墙几何，使方法差异真正来自动态行人交互。

## 验证与工件

- v2 生成器 Ruff 通过，相关测试 `13 passed`；
- 同步脚本测试 `1 passed`，WSL 9/9 文件哈希一致；
- `outputs/student/event_controlled_candidates/runtime_health_control/`
- `outputs/student/event_controlled_candidates/runtime_v2_s92500/`
- `outputs/student/event_controlled_candidates/generated/arena/map_empty/lead_stop_bounded_release_v2_train_r00_s92500.json`
