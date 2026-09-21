# PGRR 算法、场景与仿真设置示意图（初稿）

这些图是可编辑 Mermaid 源码。它们基于仓库的最终配置和 README；不是仿真截图，也不包含新实验结果。

## 图 1：算法框架

```mermaid
flowchart LR
    S[动态社会导航环境] --> O[可观测输入\nLiDAR、目标、路径、速度、规划状态、历史]
    O --> T{持续性失败？\n风险 / freeze / oscillation / deadlock / planner failure}
    T -->|否| D[DWB 局部规划器]
    T -->|是| M[规划动作 mask\n屏蔽不可达、不安全、被占用动作]
    M --> P[PGRR 策略\n25 个恢复动作]
    P --> R[21 个临时子目标\n或 WAIT / BACKUP / REPLAN / CONTINUE]
    R --> D
    D --> U[命令复用器 + 制动距离监督器]
    U --> S
    U --> Q{恢复稳定且任务有进展？}
    Q -->|是| G[恢复原始任务目标]
    G --> D

    X[训练期特权仿真真值] --> E[短时域规划专家]
    E --> L[BC / DAgger 标签]
    L --> P
```

## 图 2：最终基准的任务场景空间

```mermaid
mindmap
  root((动态社会导航基准))
    head_on_corridor
      走廊迎面相遇
    doorway_bottleneck
      门口瓶颈
    crossing_flow
      交叉人流
    blind_corner
      盲角
    group_blocking
      群体阻塞
    overtaking
      超越
    opposite_streams
      对向人流
    temporary_blockage
      临时阻塞
    每类场景
      low
      medium
      high
      每个密度五次重复
```

最终冻结基准：`8 类 × 3 种密度 × 5 次重复 = 每种方法 120 个条件`。新扩展场景必须建立新的训练/验证/测试划分，不能重用冻结测试集进行调参。

## 图 3：在线/离线环境边界

```mermaid
flowchart TB
    subgraph Offline[离线环境：Python 3.10 Conda ramp-offline]
        A[HDF5 / JSON / Parquet 数据]
        B[专家标签]
        C[BC 与 DAgger 训练]
        D[统计、图表、论文]
        E[ONNX checkpoint]
        A --> B --> C --> E
        A --> D
    end

    subgraph Online[在线环境：Ubuntu 22.04 + ROS2 Humble + 固定 Arena Gazebo]
        F[Jackal + LiDAR]
        G[Nav2 DWB]
        H[PGRR 在线推理]
        I[episode JSONL]
        F --> G
        H --> G
        G --> I
    end

    E --> H
    I --> A
```

关键规则：不要在激活 Conda 时安装或 source Arena；不要在离线测试 shell 中 source ROS。
