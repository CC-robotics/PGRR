# 作业一：DAgger 训练记录的可复现性清单（只读）

日期：2026-08-28  
状态：基于已提交 manifest 和 checkpoint 的只读核对；未重新训练，也未改动模型选择。

## 1. 这份记录回答什么问题

DAgger 不是只看“训练跑了几轮”，还要能回答：训练数据从哪里来、验证集是什么、哪个 epoch 被选中、checkpoint 是否对应，以及之后的候选为什么没有自动替换正式模型。

项目的两个可核对候选如下：

| 候选目录 | DAgger iteration | 训练样本/episode | 验证集 | 最佳验证 epoch | manifest 记录的最佳验证 loss / top-1 |
|---|---:|---:|---|---:|---:|
| `coverage_safety_aligned` | 3 | 1,387 / 12 | `multiscenario_safety_aligned_validation.h5` | 25 | 0.1784 / 0.9223 |
| `sequence_wait_aligned` | 5 | 2,002 / 14 | 同一验证集 | 20 | 0.1706 / 0.9223 |

上表是 manifest 中“各自最佳 epoch”的离线指标快照；它**不等价于**正式闭环表现，也不能单凭其中某一个数字推翻项目既有的验证选择。

## 2. 已核对的可复现身份信息

### 已选择的发布模型

- 路径：`checkpoints/dagger/coverage_safety_aligned/best.onnx`
- SHA256：`78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2`
- 发布入口：`checkpoints/final/best.onnx`
- 配置来源：`configs/imitation/bc_uniform_scenario.yaml`
- DAgger shard：`data/interim/head_on_corridor_high_train_coverage.h5`
- base dataset：`data/processed/dagger_iter1_safety_aligned_train.h5`

### 后续保留候选

- 路径：`checkpoints/dagger/sequence_wait_aligned/best.onnx`
- SHA256：`9bea4e4932b5df2e33d23ab39b74d638cdfa5789d856d39d18003bed350ac574`
- DAgger shard：`data/interim/opposite_streams_high_train_sequence_dagger.h5`
- base dataset：`data/processed/dagger_opposite_stream_train.h5`

两个 manifest 记录的验证数据哈希相同：
`5d446cd01f7219b4adaf58e0661a4a5589077c7b4f8b6b3b21ef33d187331c92`。
这说明它们使用同一份命名的 validation 数据来源；是否应以何种多指标规则选择模型，仍需结合项目既有锁定配置与闭环验证，而不是临时按单一 loss 排序。

## 3. 最小只读核对命令

在项目根目录运行：

```powershell
Get-FileHash checkpoints/dagger/coverage_safety_aligned/best.onnx -Algorithm SHA256
Get-FileHash checkpoints/dagger/sequence_wait_aligned/best.onnx -Algorithm SHA256
Get-Content data/manifests/dagger_coverage_safety_aligned_manifest.json
Get-Content data/manifests/dagger_sequence_wait_aligned_manifest.json
python scripts/student/analyze_dagger_metrics.py
```

最后一条仅将已提交 metrics JSON 汇总到
`outputs/student/dagger_diagnostic/`，不读取测试集、不更新 checkpoint，也不启动训练。

## 4. 读指标时的正确顺序

1. 先确认数据 split：训练数据、验证数据和未来保留测试不重叠；
2. 再确认专家标签和动作掩码是否一致；
3. 比较验证 loss、top-1、非法动作率、代价 regret 等多种离线指标；
4. 在配置锁定后才比较闭环结果（到达、碰撞、超时、规划失败、效率和平滑性）；
5. 不因看到保留测试结果再改 DAgger 轮数、阈值或 checkpoint。

## 5. 对“第二次 DAgger 是否过拟合”的当前结论

现在能严谨地说的是：仓库保留了多个 DAgger 候选，最终发布模型是
`coverage_safety_aligned`；较后的候选没有被自动提升为发布模型。

现在不能严谨地说的是：“第二次一定过拟合”。要验证这个假设，需要在独立 validation 上同时查看训练—验证差距、场景覆盖差异、标签分布、训练轮数与闭环表现，并在教授确认的新实验设计中预先规定选择规则。
