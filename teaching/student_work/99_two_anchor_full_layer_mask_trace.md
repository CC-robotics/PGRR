# 99 两个锚点的真实逐层mask诊断

## 本步实际执行了什么

1. 扩展mask-trace预检，使其固定4个真实运行源码的换行归一化SHA-256；
2. 为两个train-only锚点生成独立预检文件；
3. 验证Windows权威工作区和WSL运行目录均与预检源码一致；
4. Docker恢复后重新构建ROS overlay，3个包构建成功；
5. 各运行一个90秒、非冻结、只启用诊断记录的PGRR回合；
6. 原样保留两个TIMEOUT结果及全部原始JSONL、outcome和运行日志；
7. 用严格验证器检查样本数、层级顺序、格式和致命运行错误；
8. 聚合两个锚点的精确逐层结果。

## 真实运行结果

### 目标附近侧向干扰

- 终局：TIMEOUT；
- 样本：901；
- 完整逐层决策：73；
- 54/73次在`observable_scan`层首次清空全部临时子目标；
- 19/73次最终仍保留至少一个临时子目标；
- 地图层与路径层首次清空次数均为0；
- 实际选择动作只有WAIT和BACKUP。

### 前方行人停止

- 终局：TIMEOUT；
- 样本：901；
- 完整逐层决策：89；
- 69/89次在`observable_scan`层首次清空全部临时子目标；
- 20/89次最终仍保留至少一个临时子目标；
- 地图层与路径层首次清空次数均为0；
- 实际选择动作包含WAIT、BACKUP和REPLAN。

### 合并结果

- 完整逐层决策：162；
- `observable_scan`首次清空：123/162（75.93%）；
- 未清空：39/162；
- 地图层首次清空：0；
- 路径层首次清空：0；
- `observable_scan`共移除3284个逐决策临时候选；
- 路径层额外移除60个，但从未成为首次全清空层。

## 结论

第98步的“最终候选可用性不足”已由新运行的精确逐层trace重复支持，并定位到`observable_scan`层。当前证据不支持先重训策略：多数时候策略根本看不到临时子目标。下一步应审计`observable_scan`的几何判定为何在两个不同锚点中系统性地删除候选，再设计一个保持碰撞安全的最小通用改动。

该结论仍然只是两个train-only锚点上的机制诊断。尚未运行validation，不能声称跨split复现，也不能由两个TIMEOUT结果推导性能优势。

## 验证

- 两个运行验证报告均为`valid: true`；
- 两个回合样本数均与outcome匹配；
- 162/162逐层记录完整，0条格式错误；
- 导入、参数类型和恢复管理器死亡计数均为0；
- 13项聚焦测试通过；
- 未修改算法、阈值、训练数据、冻结测试或最终checkpoint。

## 主要工件

- `outputs/student/anchor_feasibility/goal_approach_full_layer_mask_trace_validation.json`
- `outputs/student/anchor_feasibility/lead_stop_full_layer_mask_trace_validation.json`
- `outputs/student/anchor_feasibility/two_anchor_full_layer_mask_summary.json`
- `data/raw/pgrr_anchor_masktrace_goalapproach_train_r00_20260915.jsonl`
- `data/raw/pgrr_anchor_masktrace_leadstop_train_r00_20260915.jsonl`
