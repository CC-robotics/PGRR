# 动作掩码、学习策略与紧急控制的责任拆分

## 分析方法

新增只读脚本 `scripts/student/analyze_recovery_control_attribution.py`。它对八类 PGRR
原始日志逐条核对 SHA-256，并把恢复决策按来源分为：

- `LEARNED_POLICY`：包含 ONNX 置信度的学习策略决策；
- `EMERGENCY_GUARD`：紧急停止、后退或脱离动作；
- `SAFETY_CLEAR`：安全状态解除后的转换；
- `RECOVERY_LIFECYCLE`：动作完成和原始目标恢复；
- `OTHER`：其余控制事件。

对于学习策略事件，脚本解析日志中最后一个 `post=` 动作集合。最后一个集合表示依次
应用日志中各项约束后，真正交给策略的合法动作。解析器已有合成测试，能够区分多个
连续约束、空集合和缺少掩码信息的情况。

## 三个假设的结果

### H1：动作掩码是否过早只剩 WAIT/BACKUP？

- 学习策略事件：60；
- 能解析最终动作集合：58；
- 最终只允许 WAIT/BACKUP：50/58，即 86.2%；
- 最终仍有其他动作：8/58；
- 两个事件没有记录可解析的最终掩码，保持为 unknown。

因此 H1 得到很强的描述性支持：绝大多数时候，模型并没有机会从临时子目标、REPLAN
或 CONTINUE 中自由选择。尤其 `closing_gap_multi_pedestrian`、
`goal_approach_lateral_interruption`、`narrow_corridor_head_on_deadlock` 和
`occluded_side_emergence` 的所有可解析学习事件都只剩 WAIT/BACKUP。

### H2：有其他合法动作时，模型是否仍偏向 WAIT/BACKUP？

8 次有替代动作的事件中：

- 4 次仍选择 WAIT/BACKUP；
- 4 次选择临时子目标；
- 没有选择掩码之外的动作。

4 次 WAIT/BACKUP 中有 3 次来自双向循环交叉场景，另 1 次来自前方行人突然停止。
样本很少，所以只能说模型偏保守仍可能是次要因素，不能据此判定 DAgger 过拟合。

### H3：紧急安全控制是否立即覆盖学习策略？

- 紧急控制事件：120，是学习事件数量的两倍；
- 其中 WAIT 64、BACKUP 32、CONTINUE 24；
- 但学习事件的下一个事件立即变成紧急控制只有 5/60。

这说明紧急控制在整个恢复过程里非常频繁，但“模型刚决策就被立即覆盖”并不是大多数
学习事件的模式。事件数量也不等于持续时间，不能把 120:60 当作控制占用比例。

## 当前优先级判断

最先应该检查 H1，即为什么碰撞风险和方向让行约束会把 86.2% 的可解析学习决策压缩到
WAIT/BACKUP。H2 应在保持同一输入和掩码的离线策略回放中检查。H3 则需要单独统计
安全状态持续时间和进入原因，不应仅凭事件次数修改安全保护。

这不是要求放松碰撞安全规则。正确方向是检查能否在保持危险动作禁止的同时，保留
至少一个经过几何验证的侧向临时子目标或受控 REPLAN，而不是为了到达率直接开放动作。

## 证据边界

这是 60 个学习事件的 train-only 描述性分析。它显示掩码约束是当前首要调查对象，
但没有随机化干预，因此不能证明掩码是超时的唯一原因，也不能支持总体性能结论。

明细输出：

- `outputs/student/eight_family_pilot/recovery_control_attribution.json`
- `outputs/student/eight_family_pilot/recovery_control_attribution.csv`
