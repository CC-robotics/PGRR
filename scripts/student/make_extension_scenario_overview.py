#!/usr/bin/env python3
"""Compose a result-free overview figure from extension smoke previews."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import image as mpimg
from matplotlib import pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PREVIEW_ROOT = ROOT / "outputs" / "student" / "extension_scenario_smoke" / "previews"
DEFAULT_OUTPUT = (
    ROOT
    / "outputs"
    / "student"
    / "extension_paper_materials"
    / "pgrr_extension_v1_task_settings.png"
)

PANELS = (
    (
        "A. Diagonal cut-in corridor",
        "diagonal_cut_in_corridor_low_train_r00_s91000.png",
        "A pedestrian crosses diagonally into the robot corridor.",
    ),
    (
        "B. Occluded side emergence",
        "occluded_side_emergence_low_train_r00_s91100.png",
        "A pedestrian emerges beside a shelf occluder and crosses the corridor.",
    ),
)


def render(preview_root: Path, output: Path) -> None:
    """Render the two prototype task settings; no outcomes are displayed."""
    figure, axes = plt.subplots(1, 2, figsize=(12.5, 5.4), constrained_layout=True)
    for axis, (title, filename, note) in zip(axes, PANELS, strict=True):
        path = preview_root / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing smoke preview: {path}")
        axis.imshow(mpimg.imread(path))
        axis.set_title(title, fontsize=12, weight="bold")
        axis.text(
            0.5,
            -0.11,
            note,
            transform=axis.transAxes,
            ha="center",
            va="top",
            fontsize=9,
            wrap=True,
        )
        axis.axis("off")
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-root", type=Path, default=DEFAULT_PREVIEW_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    render(args.preview_root.resolve(), args.output.resolve())
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
