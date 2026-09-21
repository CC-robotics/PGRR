#!/usr/bin/env python3
"""Summarize simulator-truth actor motion from one preserved episode JSONL.

This is an offline diagnostic. Privileged positions must not be used as policy
observations or training inputs.
"""

from __future__ import annotations

import argparse
import json
import math
from itertools import pairwise
from pathlib import Path
from typing import Any


def _rounded(value: float) -> float:
    return round(float(value), 6)


def _direction_reversals(values: list[float], tolerance: float = 1.0e-4) -> int:
    signs: list[int] = []
    for previous, current in pairwise(values):
        delta = current - previous
        if abs(delta) > tolerance:
            signs.append(1 if delta > 0.0 else -1)
    return sum(left != right for left, right in pairwise(signs))


def summarize_episode(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise ValueError(f"episode contains no rows: {path}")

    tracks: dict[int, list[tuple[float, float]]] = {}
    finite_nearest: list[float] = []
    for row in rows:
        privileged = row.get("privileged") or {}
        for index, position in enumerate(privileged.get("human_positions") or []):
            if len(position) >= 2:
                tracks.setdefault(index, []).append((float(position[0]), float(position[1])))
        nearest = privileged.get("nearest_human_distance")
        if nearest is not None and math.isfinite(float(nearest)):
            finite_nearest.append(float(nearest))

    actor_summaries: list[dict[str, Any]] = []
    for index, points in sorted(tracks.items()):
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        x_span = max(xs) - min(xs)
        y_span = max(ys) - min(ys)
        dominant_axis = "x" if x_span >= y_span else "y"
        dominant_values = xs if dominant_axis == "x" else ys
        step_distances = [
            math.dist(previous, current)
            for previous, current in pairwise(points)
        ]
        actor_summaries.append(
            {
                "actor_index": index,
                "valid_samples": len(points),
                "start_xy": [_rounded(value) for value in points[0]],
                "end_xy": [_rounded(value) for value in points[-1]],
                "x_range": [_rounded(min(xs)), _rounded(max(xs))],
                "y_range": [_rounded(min(ys)), _rounded(max(ys))],
                "dominant_axis": dominant_axis,
                "dominant_span_m": _rounded(max(x_span, y_span)),
                "path_length_m": _rounded(sum(step_distances)),
                "direction_reversals": _direction_reversals(dominant_values),
            }
        )

    return {
        "source": str(path),
        "sample_count": len(rows),
        "timestamp_range_s": [
            _rounded(rows[0]["timestamp"]),
            _rounded(rows[-1]["timestamp"]),
        ],
        "actor_count": len(actor_summaries),
        "actors": actor_summaries,
        "minimum_finite_robot_human_distance_m": (
            _rounded(min(finite_nearest)) if finite_nearest else None
        ),
        "diagnostic_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode_jsonl", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize_episode(args.episode_jsonl), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
