import json
from pathlib import Path

from scripts.student.analyze_privileged_actor_motion import summarize_episode


def test_summarize_episode_tracks_motion_and_reversal(tmp_path: Path) -> None:
    path = tmp_path / "episode.jsonl"
    rows = [
        {
            "timestamp": float(index),
            "privileged": {
                "human_positions": [[1.0, y]],
                "nearest_human_distance": distance,
            },
        }
        for index, (y, distance) in enumerate([(0.0, 2.0), (1.0, 1.0), (0.0, 1.5)])
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    summary = summarize_episode(path)

    assert summary["sample_count"] == 3
    assert summary["minimum_finite_robot_human_distance_m"] == 1.0
    assert summary["actors"][0]["dominant_axis"] == "y"
    assert summary["actors"][0]["dominant_span_m"] == 1.0
    assert summary["actors"][0]["path_length_m"] == 2.0
    assert summary["actors"][0]["direction_reversals"] == 1
