# PGRR technical report

Public name: **PGRR: Planning-Guided Failure-Triggered Recovery and Rejoin for
Dynamic Social Navigation**.

The report is stage-aware and fail-closed. The committed default is
`pending`, which never opens a results file and visibly leaves all numerical
pages pending.

```bash
REPORT_STAGE=pending make technical-report
```

After a completed validation run has been copied to the dedicated immutable
snapshot path, use:

```bash
REPORT_STAGE=validation \
REPORT_RESULTS=outputs/report_inputs/validation/results.parquet \
REPORT_STATISTICS=outputs/report_inputs/validation/pairwise_statistics.json \
REPORT_MATCHED_EVIDENCE=outputs/report_inputs/validation/matched_base_pgrr_evidence.json \
make technical-report
```

The locked test build accepts only:

```bash
REPORT_STAGE=test \
REPORT_RESULTS=outputs/moderate/final/results.parquet \
REPORT_STATISTICS=outputs/moderate/final/pairwise_statistics.json \
REPORT_MATCHED_EVIDENCE=outputs/moderate/final/matched_base_pgrr_evidence.json \
make technical-report
```

Historical `outputs/final`, pilot, calibration, smoke, rejected v5, live
`outputs/moderate/v6_validation`, and every `outputs/moderate/v6_validation_*`
directory are rejected before being read. For every result-bearing build, the
Parquet, statistics JSON, and matched telemetry sidecar must be siblings. The
builder rejects non-v6 scenario/pair IDs and recomputes all twelve
PGRR-versus-baseline binary
effects, confidence-interval estimates, McNemar cells, global Holm-adjusted
p-values, and matched odds ratios before rendering any number. The sidecar is
generated from SHA-verified Base/PGRR raw JSONL for a fixed outcome-independent
pair; its plots are telemetry reconstructions, not camera screenshots.
