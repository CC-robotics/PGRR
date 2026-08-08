# PGRR final presentation

Public name: **PGRR: Planning-Guided Failure-Triggered Recovery and Rejoin for
Dynamic Social Navigation**.

The supported artifacts are [`PGRR_report_zh.pptx`](PGRR_report_zh.pptx) and
[`PGRR_report_zh.pdf`](PGRR_report_zh.pdf), exactly 30 slides/pages. They are
generated from the same final 600-episode report data as the paper and
technical report:

```bash
PGRR_RELEASE_MODE=0 PGRR_RECOLLECT_RAW=0 \
scripts/reproduce_paper.sh
```

The deck contains the complete five-method outcome table, all preregistered
PGRR-versus-baseline paired terminal comparisons with global Holm correction,
joint-success efficiency costs, a SHA-verified real Gazebo GUI environment
capture, and matched Base--PGRR held-out telemetry. The GUI image is labeled as
a historical moderate-v5 validation capture (benchmark provenance, not another
current release), not a held-out camera frame; the trajectory and timeline are
not called screenshots. `speaker_notes_zh.md` provides the corresponding
30-section notes, and `contact_sheet.png` supports visual QA.

The generator still supports fail-closed `pending` and `validation` checks for
future development, but they are not separate released decks. Final slides
accept only the complete internal moderate-v6 benchmark identity and
`outputs/moderate/final/` evidence.

Historical audit boundary: an earlier 64/64 record had PGRR/Base collisions
0/24 versus 19/24, timeouts 16/24 versus 0/24, and goal reaching 8/24 versus
5/24; adjusted goal-reaching was not significant. It appears only as a
non-v6 safety--completion disclosure and is never pooled with the final result.
