# 扩展论文：算法框架图稿与图注草案

更新日期：2026-09-04  
图源：`paper/figures/drafts/pgrr_extension_system_flow.mmd`  
状态：可编辑图源与图注草案；未插入当前冻结的最终论文。

## 图要表达什么

这张图只说明系统如何工作，不用于暗示实验结果：

1. 正常时，Nav2 DWB 仍是常态控制器；
2. 只有可观测失败证据持续存在时，PGRR 才进入恢复；
3. PGRR 的高层决定受规划动作掩码约束，产生临时子目标或离散恢复动作；
4. 临时目标仍由 DWB 执行，完成后恢复原始目标；
5. 训练阶段的 simulator truth / planning expert 是虚线支路，明确不属于部署观测；
6. safety supervisor 是工程保护层，不能表述为形式化安全保证。

## 英文图注草案

> **Planning-guided failure-triggered recovery and rejoin.** Nav2 DWB remains
> the normal controller. When persistent observable interaction-failure
> evidence is detected, the recovery state machine selects a planning-masked
> temporary subgoal or recovery option through the selected DAgger policy. DWB
> executes the temporary goal before the system restores and rejoins the
> original goal. The dashed branch denotes privileged simulator/expert
> information used only for offline label generation and training; it is not a
> deployed observation. The safety supervisor is an engineering protection
> layer, not a formal safety guarantee.

## 中文讲解稿

> 左边是机器人在实际运行时能看到的信息：雷达、里程计和规划器状态。没有持续
> 失败时，DWB 一直正常导航；检测到持续风险或卡住等情况，才交给 PGRR 做短暂
> 恢复。PGRR 不直接输出速度，而是挑一个受规划约束的临时目标，仍让 DWB 去执行；
> 结束后回到原来的目标。右下的虚线是训练时教师能看到、机器人上线时看不到的
> 仿真真值和规划专家标签。

## 排版要求

- online deployment 与 offline training 用两个清晰分区；
- 特权支路必须是虚线；
- “safety supervisor”标为 engineering protection，不写 safe guarantee；
- 正式论文图中不放任何结果数字、箭头颜色暗示或未验证结论；
- 该图可先用于作业三/PPT；要放进论文时，须在独立实验的代码和协议说明稳定后再定稿。
