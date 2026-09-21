"""Opt-in, runtime-agnostic tracing for staged recovery action masks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from ramp_core.action_space import ACTION_COUNT


def _action_ids(mask: npt.ArrayLike) -> tuple[int, ...]:
    values = np.asarray(mask, dtype=np.bool_)
    if values.shape != (ACTION_COUNT,):
        raise ValueError(f"mask must have shape ({ACTION_COUNT},)")
    return tuple(int(item) for item in np.flatnonzero(values))


def _format_ids(action_ids: tuple[int, ...]) -> str:
    return ",".join(map(str, action_ids)) if action_ids else "none"


@dataclass(frozen=True, slots=True)
class MaskTransition:
    """One observed mask transition; it never owns or mutates the source masks."""

    stage: str
    before: tuple[int, ...]
    after: tuple[int, ...]
    removed: tuple[int, ...]
    added: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "before": list(self.before),
            "after": list(self.after),
            "removed": list(self.removed),
            "added": list(self.added),
        }

    def as_reason_fragment(self) -> str:
        return (
            f"mask_stage={self.stage} pre={_format_ids(self.before)} "
            f"post={_format_ids(self.after)}"
        )


class MaskTraceRecorder:
    """Collect compact mask transitions while enforcing a declared trace contract."""

    def __init__(self, *, enabled: bool = False, require_contiguous: bool = True) -> None:
        self.enabled = enabled
        self.require_contiguous = require_contiguous
        self._transitions: list[MaskTransition] = []

    @property
    def transitions(self) -> tuple[MaskTransition, ...]:
        return tuple(self._transitions)

    def record(
        self,
        stage: str,
        before_mask: npt.ArrayLike,
        after_mask: npt.ArrayLike,
        *,
        allowed_additions: tuple[int, ...] = (),
    ) -> npt.NDArray[np.bool_]:
        """Observe one stage and return a detached copy of its unchanged output mask."""

        before_array = np.asarray(before_mask, dtype=np.bool_)
        after_array = np.asarray(after_mask, dtype=np.bool_)
        before = _action_ids(before_array)
        after = _action_ids(after_array)
        result = after_array.copy()
        if not self.enabled:
            return result
        normalized_stage = stage.strip()
        if not normalized_stage:
            raise ValueError("mask trace stage must not be empty")
        if any(item.stage == normalized_stage for item in self._transitions):
            raise ValueError(f"duplicate mask trace stage: {normalized_stage}")
        if self.require_contiguous and self._transitions:
            expected = self._transitions[-1].after
            if before != expected:
                raise ValueError(
                    f"non-contiguous mask trace at {normalized_stage}: "
                    f"expected {expected}, observed {before}"
                )
        before_set = set(before)
        after_set = set(after)
        added = tuple(sorted(after_set - before_set))
        illegal_additions = set(added) - set(allowed_additions)
        if illegal_additions:
            raise ValueError(
                f"mask stage {normalized_stage} re-authorized undeclared actions: "
                f"{sorted(illegal_additions)}"
            )
        self._transitions.append(
            MaskTransition(
                stage=normalized_stage,
                before=before,
                after=after,
                removed=tuple(sorted(before_set - after_set)),
                added=added,
            )
        )
        return result

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "require_contiguous": self.require_contiguous,
            "transitions": [item.as_dict() for item in self._transitions],
        }

    def as_reason(self) -> str:
        return "; ".join(item.as_reason_fragment() for item in self._transitions)
