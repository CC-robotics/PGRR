# PGRR technical report

Public name: **PGRR: Planning-Guided Failure-Triggered Recovery and Rejoin for
Dynamic Social Navigation**.

The report is stage-aware and fail-closed. The committed default is
`pending`, which never opens a results file and visibly leaves all numerical
pages pending.

Every stage also preserves one explicitly labelled historical v1 audit summary,
which is not read from or promoted into moderate-v6 inputs: 64/64 logical
episodes; PGRR/Base collisions 0/24 versus 19/24, timeouts 16/24 versus 0/24,
and goal reaching 8/24 versus 5/24, with no significant adjusted success
difference. It documents a safety--completion trade-off, not a v6 result.

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
python scripts/paper/render_episode_media.py \
  --matched-final \
  --results outputs/moderate/final/results.parquet \
  --raw-dir data/raw \
  --scenario-root . \
  --figure-dir outputs/moderate/final/media \
  --evidence-output outputs/moderate/final/matched_base_pgrr_evidence.json

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
p-values, and matched odds ratios before rendering any number. Validation uses
the preregistered outcome-independent pair. Locked test uses the frozen
`--matched-final` rule and requires the sidecar to bind the same-pair Base/PGRR
raw, metadata, outcome, scenario, and results hashes to the fixed files
`moderate_matched_base_pgrr_trajectory.pdf` and
`moderate_pgrr_recovery_timeline.pdf`. Both are telemetry reconstructions, not
camera screenshots. The report separately requires the SHA- and episode-bound
real Gazebo GUI capture from the audited frozen-v5 demonstration.
