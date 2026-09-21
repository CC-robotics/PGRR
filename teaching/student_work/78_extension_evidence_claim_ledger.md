# 作业三/论文：扩展实验“证据—表述”台账

## 做了什么

新增生成器 `scripts/student/build_extension_claim_ledger.py`，从已经提交的 CSV/JSON
自动生成：

- `outputs/student/paper_claim_ledger/extension_claim_ledger.json`
- `outputs/student/paper_claim_ledger/extension_claim_ledger.md`

台账把每组数字与可写表述、禁止推论和源文件绑定。这样以后写作时不会把 train-only
诊断、静态预检或 mask 轨迹误写成 held-out 性能结果。

## 当前五组可写材料

1. 八个 train-only 开发配对中，Base 有 6 次碰撞；PGRR 无碰撞，但也没有到达目标。
   这只能描述安全—完成权衡，不能声称优越或显著。
2. 显式恢复进展合约检查了 30 个 train 循环，0 个达到该探针的任务进展要求；这是
   原型诊断，不是因果归因，也不是运行时阈值选择。
3. 两个 selector-positive train 回合共得到 159 个完整 mask 分层决策轨迹；跨 split
   复制尚未成立，不能据此声称 mask 导致性能变化。
4. validation 审计区分了对角场景的 detector-negative 和 head-on 的 emergency-only；
   不能再笼统写成“两个 validation 都一直处于 NORMAL”。
5. lead-stop validation 候选只完成静态预检，尚无运行结果。

## 验证与论文边界

两个单元测试验证真实源数据能生成预期台账，并确认未就绪的 validation 预检会被拒绝。
所有数字均来自台账列出的 checked-in CSV/JSON。该工作没有修改 `paper/main.tex`，也没有
把开发诊断加入正式论文结果；它只是为后续写作建立一道可复核的边界检查。

