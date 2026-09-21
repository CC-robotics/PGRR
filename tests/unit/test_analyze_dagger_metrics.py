from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _module():  # type: ignore[no-untyped-def]
    path = ROOT / "scripts" / "student" / "analyze_dagger_metrics.py"
    spec = importlib.util.spec_from_file_location("analyze_dagger_metrics", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_metrics(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "train_samples": 12,
                "validation_samples": 4,
                "history": [
                    {
                        "epoch": 1,
                        "train": {"loss": 0.8, "top1": 0.5},
                        "validation": {"loss": 0.9, "top1": 0.4},
                    },
                    {
                        "epoch": 2,
                        "train": {"loss": 0.4, "top1": 0.8},
                        "validation": {"loss": 0.6, "top1": 0.7},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def test_service_preserves_student_output_names_and_content(tmp_path: Path) -> None:
    module = _module()
    run_dir = tmp_path / "dagger_round"
    run_dir.mkdir()
    metrics = run_dir / "metrics.json"
    _write_metrics(metrics)

    result = module.DaggerMetricsService().run(
        module.DaggerMetricsRequest(metrics=(metrics,), output_dir=tmp_path / "output")
    )

    assert result.csv_path.name == "dagger_metrics_summary.csv"
    assert result.markdown_path.name == "dagger_metrics_summary.md"
    assert "best_val_loss" in result.csv_path.read_text(encoding="utf-8")
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "# DAgger metrics: read-only comparison" in markdown
    assert "not proof of overfitting" in markdown


def test_existing_cli_arguments_become_request(tmp_path: Path) -> None:
    module = _module()
    metrics = tmp_path / "metrics.json"
    _write_metrics(metrics)

    request = module.parse_request([str(metrics), "--output-dir", str(tmp_path / "output")])

    assert request.metrics == (metrics,)
    assert request.output_dir == tmp_path / "output"
