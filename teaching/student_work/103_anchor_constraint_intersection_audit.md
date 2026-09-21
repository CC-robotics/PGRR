# 103 锚点约束交集精确审计

## 本步实际执行了什么

从两次最新 train-only 运行逐条重建扫描层以后的临时动作集合，检查扫描层残余候选究竟在哪个后续约束中消失，并将动作 ID 映射回固定动作空间的半径和角度。

## 结果

- 共 89 次恢复决策，最终 89 次均无临时子目标；
- 55 次首先由 `observable_scan` 清空；
- 其余 34 次扫描层只留下动作 2；
- 动作 2 是 0.6 m、-30°（机器人坐标系右前方）的临时子目标；
- 34/34 次动作 2 都被 `bc_yield_mask` 删除；
- 没有一次临时动作真正交给 learned selector，也没有一次临时动作被选择。

## 通俗解释

扫描规则说“右前方这一小步没有碰撞”，但让行规则又说“现在几乎不能朝任务方向前进”，于是唯一幸存动作仍不合法。问题是两个单独合理的安全约束组合后没有共同可用动作，而不是模型看见安全动作后偏爱后退。

## 工件

- `outputs/student/anchor_feasibility/two_anchor_constraint_intersection.{json,md}`
- `scripts/student/audit_anchor_constraint_intersection.py`
- 3 项单元测试和 Ruff 通过。

本步没有调整阈值、候选动作或模型，也没有运行冻结测试。
