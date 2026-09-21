# 116 八个论文案例的证据就绪审计

> 口径更正（2026-09-16）：这里审计的是 8 条冻结 episode 例子，而不是
> 教授要求的 8 个可复现场景。证据“可用”仅表示能够支持辅助结果表，
> 不表示八场景研究任务已经完成。

本轮没有重跑冻结实验，而是逐一核对 8 个定性案例的五方法结果行、episode ID、恢复次数、场景文件、原始 JSONL/sidecar 和既有论文媒体。

## 结论

- **结果表证据：8/8 就绪。** 每个案例在冻结 `results.parquet` 中都有 Base、Standard、Heuristic、Uniform BC、PGRR 五行完整结果，可直接形成论文案例对照表。
- **本地场景 JSON：0/8。** 结果中保存了路径与 SHA-256，但对应生成文件不在当前 Windows 或 WSL 工作副本中。
- **可重新绘制轨迹：0/8。** 当前未保留这些 episode 的 JSONL、metadata 和 outcome sidecar，不能据空缺数据重新构造轨迹，也不能重跑冻结测试来替代。
- **既有发布图：1/8。** `blind_corner/high/seed 87320` 已有 SHA-256 验证的 Base–PGRR 轨迹图与 PGRR 恢复时间线，并明确标注为遥测重建而非相机截图。

因此论文现在可以安全推进“八案例结果表 + 一个代表性轨迹图”。若教授希望每个案例都有轨迹图，需要从原始实验归档找回 JSONL 和 sidecar；在找回前不能补画或伪造。

## 产物与验证

- `scripts/student/audit_paper_case_evidence.py`
- `tests/unit/test_audit_paper_case_evidence.py`
- `outputs/student/paper_case_shortlist/case_evidence_audit.json`
- `outputs/student/paper_case_shortlist/case_evidence_audit.md`
- `outputs/student/paper_case_shortlist/case_metrics_long.csv`

Ruff 通过；案例选择器与证据审计合计 4 项单元测试通过。
