# 101 原始LaserScan谓词精确诊断

## 本步实际执行了什么

1. 为`apply_observable_scan_mask`增加可选诊断输出；默认关闭且不改变返回mask；
2. trace开启时记录原始运行时LaserScan上的方向净空通过ID、胶囊扫掠通过ID和实际净空参数；
3. 将5个运行源码纳入哈希白名单，备份并同步到WSL，5/5一致；
4. ROS overlay重新构建3/3包成功；
5. 重跑两个非冻结train-only锚点并原样保留两个TIMEOUT；
6. 严格验证192/192条trace完整，并验证scan输出逐条等于进入动作、方向通过与胶囊通过三者交集。

## 精确结果

- 目标附近侧向干扰：89条决策，54次scan层清空，89次均使用0.90米锁存净空；
- 前方行人停止：103条决策，68次scan层清空，另有15次由路径走廊最终清空；其中64次使用0.90米、39次使用正常0.25/0.48米净空；
- 合并192条决策中，122次scan层清空；这122次全部属于“胶囊谓词没有任何进入动作通过”，没有一条由方向谓词先单独清空；
- 4032个逐动作机会中，315次两个谓词都通过，556次方向通过但胶囊失败，3161次两个都失败；没有出现方向失败但胶囊通过；
- 所有1.4米动作的胶囊通过次数为0；1.0米动作只有-30度通过过55次；0.6米动作承担其余全部通过。

## 正确解释

现在可以精确说：在这两个train-only锚点中，scan层全清空的直接共同条件是整段胶囊扫掠检查，而不是单纯的目标方向距离检查。但当前二值谓词尚不能区分胶囊失败发生在起点重叠、运动途中还是终点附近，也不能据此断言0.90米安全余量应该降低。

## 下一安全步骤

继续增加只读几何诊断：记录每个动作的最小线段净空及失败区段/初始重叠类别。之后先在train/validation做候选生成的离线设计，不直接修改正式阈值或模型。

## 工件与验证

- `outputs/student/anchor_feasibility/two_anchor_exact_scan_predicates.{json,md}`
- `outputs/student/anchor_feasibility/{goal_approach,lead_stop}_predicate_trace_validation.json`
- `scripts/student/summarize_exact_scan_predicates.py`
- 27项相关测试、Ruff和diff检查通过；未触碰冻结测试、最终checkpoint或最终证据。
