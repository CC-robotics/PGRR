import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/student/validate_observation_shadow_smoke.py"
SPEC = importlib.util.spec_from_file_location("validate_observation_shadow_smoke", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_fixture(tmp_path: Path, summary: dict | None, runtime_extra: str = ""):
    outcome = tmp_path / "episode.outcome.json"
    outcome.write_text(
        json.dumps({"episode_id": "shadow_train", "outcome": "TIMEOUT"}),
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime.log"
    line = ""
    if summary is not None:
        line = "[INFO] observation_shadow_summary=" + json.dumps(summary) + "\n"
    runtime.write_text(line + runtime_extra, encoding="utf-8")
    return outcome, runtime


def _valid_summary() -> dict:
    return {
        "comparison_count": 12,
        "equivalent_count": 12,
        "mismatch_count": 0,
        "stored_per_sample_records": 0,
        "authoritative_path_changed": False,
    }


def test_accepts_one_bounded_exact_summary_regardless_of_episode_outcome(
    tmp_path: Path,
) -> None:
    result = MODULE.validate_smoke(*_write_fixture(tmp_path, _valid_summary()))

    assert result["valid"]
    assert result["comparison_count"] == 12
    assert result["outcome"] == "TIMEOUT"
    assert not result["performance_claim"]


def test_rejects_missing_or_zero_comparison_summary(tmp_path: Path) -> None:
    missing = MODULE.validate_smoke(*_write_fixture(tmp_path, None))
    zero = _valid_summary() | {"comparison_count": 0, "equivalent_count": 0}
    empty = MODULE.validate_smoke(*_write_fixture(tmp_path, zero))

    assert not missing["valid"]
    assert not empty["valid"]


def test_rejects_mismatch_or_authority_change(tmp_path: Path) -> None:
    mismatch = _valid_summary() | {"equivalent_count": 11, "mismatch_count": 1}
    changed = _valid_summary() | {"authoritative_path_changed": True}

    assert not MODULE.validate_smoke(*_write_fixture(tmp_path, mismatch))["valid"]
    assert not MODULE.validate_smoke(*_write_fixture(tmp_path, changed))["valid"]


def test_rejects_duplicate_summary_or_runtime_failure(tmp_path: Path) -> None:
    summary = _valid_summary()
    duplicate = "observation_shadow_summary=" + json.dumps(summary) + "\n"
    duplicated = MODULE.validate_smoke(
        *_write_fixture(tmp_path, summary, runtime_extra=duplicate)
    )
    failed = MODULE.validate_smoke(
        *_write_fixture(tmp_path, summary, runtime_extra="ImportError: broken\n")
    )

    assert not duplicated["valid"]
    assert not failed["valid"]
