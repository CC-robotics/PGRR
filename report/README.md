# PGRR technical report

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
make technical-report
```

The locked test build accepts only:

```bash
REPORT_STAGE=test \
REPORT_RESULTS=outputs/moderate/final/results.parquet \
REPORT_STATISTICS=outputs/moderate/final/pairwise_statistics.json \
make technical-report
```

Historical `outputs/final`, pilot, calibration, smoke, and the live
`outputs/moderate/v5_validation` directory are rejected before being read.
For every result-bearing build, the Parquet and statistics JSON must be
siblings. The builder recomputes all twelve PGRR-versus-baseline binary
effects, confidence-interval estimates, McNemar cells, global Holm-adjusted
p-values, and matched odds ratios before rendering any number.
