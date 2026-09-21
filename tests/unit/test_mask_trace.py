from __future__ import annotations

import numpy as np
import pytest
from ramp_core.action_space import ACTION_COUNT, CONTINUE_ACTION_ID, WAIT_ACTION_ID
from ramp_core.recovery.mask_trace import MaskTraceRecorder


def _mask(*action_ids: int) -> np.ndarray:
    mask = np.zeros(ACTION_COUNT, dtype=np.bool_)
    mask[list(action_ids)] = True
    return mask


def test_disabled_trace_returns_copy_without_collecting() -> None:
    recorder = MaskTraceRecorder(enabled=False)
    source = _mask(0, WAIT_ACTION_ID)

    observed = recorder.record("map", np.ones(ACTION_COUNT, dtype=np.bool_), source)

    assert np.array_equal(observed, source)
    assert observed is not source
    assert recorder.transitions == ()


def test_trace_records_contiguous_monotonic_stages() -> None:
    recorder = MaskTraceRecorder(enabled=True)
    initial = np.ones(ACTION_COUNT, dtype=np.bool_)
    mapped = initial.copy()
    mapped[[2, 3]] = False
    scanned = mapped.copy()
    scanned[0] = False

    recorder.record("map_connectivity", initial, mapped)
    result = recorder.record("observable_scan", mapped, scanned)

    assert np.array_equal(result, scanned)
    assert recorder.transitions[0].removed == (2, 3)
    assert recorder.transitions[1].removed == (0,)
    assert "mask_stage=observable_scan" in recorder.as_reason()
    assert recorder.as_dict()["transitions"][1]["after"] == list(
        np.flatnonzero(scanned)
    )


def test_trace_rejects_gap_duplicate_and_undeclared_reauthorization() -> None:
    recorder = MaskTraceRecorder(enabled=True)
    initial = _mask(0, WAIT_ACTION_ID)
    reduced = _mask(WAIT_ACTION_ID)
    recorder.record("map", initial, reduced)

    with pytest.raises(ValueError, match="non-contiguous"):
        recorder.record("scan", initial, reduced)
    with pytest.raises(ValueError, match="duplicate"):
        recorder.record("map", reduced, reduced)
    with pytest.raises(ValueError, match="re-authorized"):
        recorder.record("special", reduced, _mask(WAIT_ACTION_ID, CONTINUE_ACTION_ID))


def test_trace_allows_declared_special_action_addition() -> None:
    recorder = MaskTraceRecorder(enabled=True)
    before = _mask(WAIT_ACTION_ID)
    after = _mask(WAIT_ACTION_ID, CONTINUE_ACTION_ID)

    recorder.record(
        "special_action_authorization",
        before,
        after,
        allowed_additions=(CONTINUE_ACTION_ID,),
    )

    assert recorder.transitions[0].added == (CONTINUE_ACTION_ID,)
