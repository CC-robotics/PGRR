# 98 两个锚点场景的恢复失败诊断

## 本步完成了什么

新增可复现脚本 `scripts/student/build_anchor_failure_diagnosis.py`，把以下四份已经核验的 train-only 工件合并为一份两锚点诊断：

- 八类 Base/PGRR 最小配对结果；
- 恢复周期与原目标进展诊断；
- 学习决策和安全 mask 归因；
- 恢复周期进展契约探针。

锚点场景为：

- `goal_approach_lateral_interruption`；
- `lead_pedestrian_sudden_stop`。

生成物：

- `outputs/student/anchor_feasibility/two_anchor_failure_diagnosis.json`
- `outputs/student/anchor_feasibility/two_anchor_failure_diagnosis.md`

## 结果

- Base 在两个锚点中均碰撞，PGRR均超时；
- 两个PGRR回合共有6个恢复周期；
- 6/6周期的危险均按当前训练期契约解除；
- 0/6周期产生有意义的原目标进展；
- 前方行人停止场景完成4次重入，但5个周期均为非正进展；
- 15次学习决策中，13次（86.67%）的最终mask只允许WAIT和BACKUP；
- 只有2次学习决策存在其他候选动作，且都来自前方行人停止场景；
- 目标附近侧向干扰的5次学习决策全部只允许WAIT/BACKUP。

## 当前判断

首要问题更像“候选动作可用性不足”，而不只是模型在多个安全临时子目标中选错：多数决策到达策略前已经只剩WAIT和BACKUP。但历史锚点日志没有精确保存所有上游mask层，因此这个结论是定位线索，不是因果证明。

“完成重入”也不等于“恢复成功”。前方行人停止场景虽然4次恢复原目标，却没有任何恢复周期带来正进展，说明后续评价必须同时检查危险解除、重入和任务进展。

## 下一门禁

在修改候选过滤、策略或阈值前，分别为两个锚点运行一次非冻结的完整逐层mask trace，确定临时子目标首先在哪一层被移除。只有得到精确层级证据后，才选择一个通用修改，并在train/validation上验证。

## 验证与边界

- 3/3聚焦单元测试通过；
- Ruff通过；
- JSON解析通过；
- 四个输入工件的SHA-256写入输出；
- 未运行Arena、训练或评测；
- 未修改冻结测试集、最终checkpoint或算法阈值；
- 两个单次train-only回合不能证明因果、泛化或PGRR优越性。
