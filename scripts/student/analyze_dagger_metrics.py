"""Read-only comparison of checked-in DAgger training metric JSON files.

This helper writes a small CSV and Markdown table for discussion.  It does not
train a model, change a checkpoint, or access the frozen test set.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DaggerMetricsRequest:
    """CLI-independent request for a read-only DAgger metric comparison."""

    metrics: tuple[Path, ...]
    output_dir: Path


@dataclass(frozen=True)
class DaggerMetricsResult:
    """Artifacts written by :class:`DaggerMetricsService`."""

    csv_path: Path
    markdown_path: Path


def best_epoch(history: list[dict], split: str, metric: str, maximize: bool) -> dict:
    def key(row: dict) -> float:
        return float(row[split][metric])

    return (max if maximize else min)(history, key=key)


def summarize(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    history = payload["history"]
    min_loss = best_epoch(history, "validation", "loss", maximize=False)
    max_top1 = best_epoch(history, "validation", "top1", maximize=True)
    final = history[-1]
    return {
        "run": path.parent.name,
        "metrics_path": str(path),
        "train_samples": payload.get("train_samples"),
        "validation_samples": payload.get("validation_samples"),
        "epochs": len(history),
        "best_val_loss_epoch": min_loss["epoch"],
        "best_val_loss": min_loss["validation"]["loss"],
        "train_loss_at_best_val_loss": min_loss["train"]["loss"],
        "loss_gap_at_best_val_loss": min_loss["validation"]["loss"] - min_loss["train"]["loss"],
        "best_val_top1_epoch": max_top1["epoch"],
        "best_val_top1": max_top1["validation"]["top1"],
        "train_top1_at_best_val_top1": max_top1["train"]["top1"],
        "top1_gap_at_best_val_top1": max_top1["train"]["top1"] - max_top1["validation"]["top1"],
        "final_train_loss": final["train"]["loss"],
        "final_val_loss": final["validation"]["loss"],
        "final_train_top1": final["train"]["top1"],
        "final_val_top1": final["validation"]["top1"],
        "final_loss_gap": final["validation"]["loss"] - final["train"]["loss"],
        "final_top1_gap": final["train"]["top1"] - final["validation"]["top1"],
    }


class DaggerMetricsService:
    """Read metrics and render the historical student-facing CSV/Markdown outputs."""

    def run(self, request: DaggerMetricsRequest) -> DaggerMetricsResult:
        rows = [summarize(path) for path in request.metrics]
        request.output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = request.output_dir / "dagger_metrics_summary.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        md_path = request.output_dir / "dagger_metrics_summary.md"
        headers = [
            "run",
            "train_samples",
            "epochs",
            "best_val_loss",
            "loss_gap_at_best_val_loss",
            "best_val_top1",
            "top1_gap_at_best_val_top1",
            "final_val_loss",
            "final_loss_gap",
            "final_val_top1",
            "final_top1_gap",
        ]
        lines = [
            "# DAgger metrics: read-only comparison",
            "",
            "| " + " | ".join(headers) + " |",
            "|" + "|".join(["---"] * len(headers)) + "|",
        ]
        for row in rows:
            values = [
                f"{row[header]:.4f}" if isinstance(row[header], float) else str(row[header])
                for header in headers
            ]
            lines.append("| " + " | ".join(values) + " |")
        lines += [
            "",
            "Gap definition: loss gap = validation loss - training loss; "
            "top-1 gap = training top-1 - validation top-1.",
            "Interpretation boundary: a positive gap is a diagnostic clue, not proof "
            "of overfitting. This table does not establish closed-loop superiority.",
        ]
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return DaggerMetricsResult(csv_path=csv_path, markdown_path=md_path)


def parse_request(argv: Sequence[str] | None = None) -> DaggerMetricsRequest:
    """Keep the established CLI while separating parsing from the service."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metrics", nargs="+", type=Path, help="metrics.json files")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    return DaggerMetricsRequest(metrics=tuple(args.metrics), output_dir=args.output_dir)


def main(argv: Sequence[str] | None = None) -> None:
    result = DaggerMetricsService().run(parse_request(argv))
    print(f"Wrote {result.csv_path}")
    print(f"Wrote {result.markdown_path}")


if __name__ == "__main__":
    main()
