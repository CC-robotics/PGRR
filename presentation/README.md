# PGRR presentation

The presentation contains exactly 30 Chinese slides. Its slide specification
and speaker notes are usable in `pending` mode without any numerical results.

```bash
conda run -n ramp-offline python scripts/presentation/build_deck.py \
  --stage pending --check-only
```

PPTX generation requires `python-pptx` in the isolated `ramp-offline`
environment. The generator prints a precise dependency error when it is not
installed; it never attempts to install packages or modify ROS/Arena.

All result-bearing slides consume `report/generated/report_data.json`, which
is produced by the fail-closed report asset builder. They do not read result
Parquet files directly. Slide 24 displays all four PGRR-versus-baseline
comparisons for goal reaching, collision, and timeout, including paired 95%
confidence intervals, global Holm-adjusted p-values, and matched odds ratios.
