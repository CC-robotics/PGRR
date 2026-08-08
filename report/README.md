# PGRR final technical report

Public name: **PGRR: Planning-Guided Failure-Triggered Recovery and Rejoin for
Dynamic Social Navigation**.

The supported artifact is
[`PGRR_technical_report_zh.pdf`](PGRR_technical_report_zh.pdf): an exact
32-page Chinese report generated from the final 600-episode evidence bundle.
Rebuild it through the project-wide fail-closed pipeline:

```bash
PGRR_RELEASE_MODE=0 PGRR_RECOLLECT_RAW=0 \
scripts/reproduce_paper.sh
```

For a report-only rebuild from the same final inputs:

```bash
REPORT_STAGE=test \
REPORT_RESULTS=outputs/moderate/final/results.parquet \
REPORT_STATISTICS=outputs/moderate/final/pairwise_statistics.json \
REPORT_MATCHED_EVIDENCE=outputs/moderate/final/matched_base_pgrr_evidence.json \
make technical-report
```

The builder requires 600 rows, 120 shared conditions per method, a complete
five-method set, exact paired statistics, and the matched telemetry sidecar. It
rejects historical, pilot, smoke, calibration, live validation, partial, or
non-v6 inputs before rendering a final number. Development-only `pending` and
`validation` modes remain fail-closed implementation features; they are not
alternative released reports.

The report includes a SHA-bound real Gazebo GUI capture and a final same-pair
Base--PGRR trajectory/timeline comparison. The former is labeled as a real
historical moderate-v5 validation environment capture (benchmark provenance,
not another current release), not a held-out camera frame; the latter is
labeled as telemetry reconstruction, not a screenshot.

Historical audit boundary: an earlier 64/64 record had PGRR/Base collisions
0/24 versus 19/24, timeouts 16/24 versus 0/24, and goal reaching 8/24 versus
5/24; adjusted goal-reaching was not significant. It is disclosed as a
safety--completion trade-off and is never pooled with the final moderate-v6
evidence.
