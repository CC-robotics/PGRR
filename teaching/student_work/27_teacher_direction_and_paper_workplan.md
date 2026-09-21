# 老师逐项回复后的执行与论文工作单

来源：`C:\Users\28646\Desktop\学生问题逐项回复.pdf`（23 页）  
整理日期：2026-09-04  
状态：老师已明确的方向；现有 `moderate_v6` 发布证据保持冻结。

## 1. 已明确的作业二边界

老师要求的第一阶段不是重写 `RecoveryManager`、动作掩码、专家代价、网络、状态机或 ROS 运行行为。

应新增纯 Python 的“制品与阶段接口层”：

```text
packages/ramp_core/ramp_core/pipeline/
  contracts.py  # 场景、数据、checkpoint、评测制品的契约
  io.py         # 制品路径和哈希的读写/校验边界
  ports.py      # CLI 到 service 的可替换端口
```

目标是使现有命令逐步变为：

```text
argparse -> request dataclass -> service -> 原格式输出
```

验收条件：旧 CLI 兼容；既有测试通过；最终发布 96 个 artifact 的路径、大小和 SHA 不变。

## 2. 已明确的作业四方向

新 benchmark 固定使用独立身份：`pgrr_extension_v1`。

优先候选场景：

1. `diagonal_cut_in_corridor`：行人从斜向切入机器人前方；
2. `occluded_side_emergence`：行人从 shelf 遮挡后出现并横穿；
3. 可选 `turning_cross_flow`：多 waypoint 的近似转向/汇流。

老师给出的 seed 规则：

```text
seed = B_split + 100 * family_index + 10 * density_index + repeat_index
train B = 91000, validation B = 93000, test B = 97000
```

每个 family-density cell 的重复数是 train/validation/test = 6/3/5。
新数据按完整 episode 切分；scenario、seed、JSON SHA 和几何实现跨 split 不重叠；DAgger 数据只来自 train。

当前 runtime 固定 `map_empty`，因此近期目标应是新场景的 train/validation 编译与 smoke；跨地图 held-out test 要等 world/map 参数化真正完成，不能只修改 `map_id`。

## 3. 论文部分应逐步推进什么

现有最终论文与其 600 回合证据保持不改。后续应准备一份“扩展实验论文素材包”，并随工程进度增加内容：

| 工程阶段 | 同步形成的论文材料 | 当前状态 |
|---|---|---|
| 接口层重构 | 系统实现图、接口表、等价测试表 | 可开始整理 |
| 新场景配置 | 任务场景图、变量表、split/seed 表 | 可开始整理 |
| train/validation smoke | 运行设置、日志完整性、非结果性基础设施说明 | 待新场景实现 |
| 模型选择 | 训练/验证曲线、checkpoint 选择规则 | 待独立训练决定 |
| held-out test | 主结果表、配对统计、轨迹与失败分析 | 必须等配置冻结后 |

建议的扩展论文主线：

> PGRR preserves DWB for normal control and invokes a planning-constrained,
> interpretable recovery-and-rejoin policy only after persistent observable
> dynamic-interaction failures.  The empirical question is whether this
> safety/completion benefit persists under independently defined cut-in and
> occlusion scenarios, while reporting efficiency and smoothness costs.

中文工作表述：

> 在保持 Nav2 DWB 常态控制的前提下，研究 PGRR 是否能在独立定义的斜切入和遮挡突现交互中，通过受规划约束的可解释恢复与原任务重接，维持经验安全和任务完成收益，并如实报告效率与平滑性代价。

## 4. 这次已完成的第一项落实

已新增 `ramp_core.pipeline` 的最小骨架：

- `contracts.py`：制品类别、路径/哈希引用、阶段请求与结果契约；
- `io.py`：只读 SHA-256 与仓库相对路径描述；
- `ports.py`：未来 CLI/service 适配的协议；
- `tests/unit/test_pipeline_contracts.py`：路径、哈希、阶段输出一致性测试。

它尚未接管任何既有 CLI，因此不会改变现有训练、评测或 ROS 行为。

随后已在学生专用的只读 `analyze_dagger_metrics.py` 上完成第一例兼容适配：

```text
argparse -> DaggerMetricsRequest -> DaggerMetricsService -> 原有 CSV/Markdown 输出
```

参数名、输出文件名和终端 `Wrote ...` 提示保持不变；该脚本不读取测试集、不训练、
不更改 checkpoint。

## 5. 接下来的建议顺序

1. 为一个现有的只读/非发布脚本演示 `argparse -> request -> service` 适配，并用兼容测试锁住原输出；
2. 为 `pgrr_extension_v1` 增加仅 train/validation 的场景 catalog 草案、seed 编译检查与配置审计；
3. 先完成两个新场景族的 smoke 与预览，再考虑独立训练；
4. 同步将场景变量、运行设置和接口图排成可进入扩展论文的图表草稿；
5. 在代码、checkpoint、统计协议和场景冻结前，不开启新 held-out test。
