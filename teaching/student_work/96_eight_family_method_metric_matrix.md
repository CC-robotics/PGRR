# 96 八类场景的算法—场景—指标矩阵

## 本步完成了什么

新增可复现生成器 `scripts/student/build_eight_family_method_metric_matrix.py`，从已签入的八类场景 draft/pilot YAML 与 train-only 最小配对 CSV 中，生成作业三和论文可使用的八类场景—算法机制—评价指标对应表。

生成物：

- `outputs/student/paper_design/eight_family_method_metric_matrix.json`
- `outputs/student/paper_design/eight_family_method_metric_matrix.md`

## 这张矩阵解决了什么问题

它把分散的配置和运行记录连成一条可审计链路：

`场景扰动 -> 经典规划正常控制 -> 失败触发 -> 恢复动作/临时子目标 -> 经典规划执行 -> 恢复原目标并重入 -> 分层报告指标`

后续实验将明确区分：

1. **主要结局**：GOAL_REACHED、COLLISION、TIMEOUT，每个回合都保留；
2. **成功代价**：完成时间、路径长度、角加加速度，仅在双方共同成功时比较；
3. **机制诊断**：触发、恢复周期、动作切换、临时子目标、REPLAN、原目标恢复等。

## 当前真实观察与边界

当前八个最小配对仅是 train-only 机制开发观察，不能证明泛化、总体优越性或统计显著性。Base 在八类中出现 6 次碰撞和 2 次超时；PGRR 出现 7 次超时和 1 次规划失败。这说明场景确实能制造困难，也说明当前 PGRR 在这些扩展原型上尚未形成“安全且完成”的正面结果，不能包装成论文结论。

矩阵也保留原型限制。例如“突然停止”目前由行人到达终点后保持实现，并非独立刹车事件；“closing gap”是中心线收缩原型，并非直接控制标量间隙宽度。

## 验证

- 聚焦单元测试：3/3 通过；
- Ruff：通过；
- 生成 JSON 可由 `json.tool` 完整解析；
- 八类场景 8/8 均有算法组件、主要指标、机制诊断和解释边界；
- 未运行 Arena、训练或最终评测；
- 未读取或修改冻结 `moderate_v6` 测试集、`outputs/moderate/final`、最终 checkpoint 或算法阈值。

## 下一步

检查矩阵中各机制诊断字段能否由现有 telemetry 直接得到，形成“已有 / 可派生 / 尚缺失”的字段覆盖表。这样恢复运行环境后，可以优先补最小记录能力，避免先跑大量实验再发现关键指标没有记录。
