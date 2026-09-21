from pathlib import Path

from scripts.student.audit_recovery_manager_structure import audit_source


def test_audit_reports_method_spans_calls_and_seams(tmp_path: Path) -> None:
    source = tmp_path / "node.py"
    source.write_text(
        "class RecoveryManagerNode:\n"
        "    def _observation(self):\n"
        "        return self._laser_clearance() + self.value\n"
        "    def _laser_clearance(self):\n"
        "        return 1\n"
        "    def _action_mask(self):\n"
        "        return self._observation()\n",
        encoding="utf-8",
    )
    report = audit_source(source)
    methods = {item["name"]: item for item in report["methods"]}
    assert report["method_count"] == 3
    assert methods["_observation"]["internal_method_calls"] == ["_laser_clearance"]
    assert methods["_observation"]["self_attribute_count"] == 2
    assert report["candidate_seams"]["observation_and_geometry"]["method_count"] == 2
    assert "_select_decision" in report["candidate_seams"]["mask_and_policy_selection"][
        "missing_expected_methods"
    ]


def test_audit_rejects_missing_class(tmp_path: Path) -> None:
    source = tmp_path / "other.py"
    source.write_text("class Other:\n    pass\n", encoding="utf-8")
    try:
        audit_source(source)
    except ValueError as error:
        assert "class not found" in str(error)
    else:
        raise AssertionError("missing class must be rejected")
