"""Small deterministic temporal metrics used by failure rules."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


def path_displacement(positions: npt.ArrayLike) -> float:
    array = np.asarray(positions, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 2 or len(array) == 0:
        raise ValueError("positions must have shape [T, 2] with T > 0")
    return float(np.linalg.norm(array[-1] - array[0]))


def goal_progress(distances: npt.ArrayLike) -> float:
    array = np.asarray(distances, dtype=np.float64)
    if array.ndim != 1 or len(array) == 0:
        raise ValueError("distances must have shape [T] with T > 0")
    return float(array[0] - array[-1])


def angular_sign_changes(values: npt.ArrayLike, deadband: float) -> int:
    if deadband < 0.0:
        raise ValueError("deadband must be non-negative")
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1:
        raise ValueError("angular velocities must be one-dimensional")
    signs = np.sign(array[np.abs(array) > deadband])
    if len(signs) < 2:
        return 0
    return int(np.count_nonzero(signs[1:] != signs[:-1]))
