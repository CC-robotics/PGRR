# DAgger metrics: read-only comparison

| run | train_samples | epochs | best_val_loss | loss_gap_at_best_val_loss | best_val_top1 | top1_gap_at_best_val_top1 | final_val_loss | final_loss_gap | final_val_top1 | final_top1_gap |
|---|---|---|---|---|---|---|---|---|---|---|
| coverage_safety_aligned | 2774 | 30 | 0.1784 | 0.0859 | 0.9323 | 0.0432 | 0.1879 | 0.1111 | 0.9098 | 0.0682 |
| sequence_wait_aligned | 4004 | 27 | 0.1706 | 0.0130 | 0.9398 | -0.0552 | 0.2297 | 0.0994 | 0.9148 | 0.0438 |

Gap definition: loss gap = validation loss − training loss; top-1 gap = training top-1 − validation top-1.
Interpretation boundary: a positive gap is a diagnostic clue, not proof of overfitting. This table does not establish closed-loop superiority.
