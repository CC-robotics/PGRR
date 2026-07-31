"""ONNX inference for the observable recovery policy."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt
from ramp_core.action_space import ACTION_COUNT
from ramp_core.observations import RecoveryObservation
from ramp_core.types import RecoveryDecision


class _InputDescriptor(Protocol):
    name: str


class _InferenceSession(Protocol):
    def get_inputs(self) -> list[_InputDescriptor]: ...

    def run(
        self,
        output_names: list[str] | None,
        input_feed: dict[str, npt.NDArray[np.generic]],
    ) -> list[npt.NDArray[np.generic]]: ...


def encode_observation(
    observation: RecoveryObservation,
    *,
    lidar_max_m: float = 6.0,
) -> tuple[npt.NDArray[np.float32], npt.NDArray[np.float32]]:
    """Encode the exact public observation schema used by offline training."""
    if lidar_max_m <= 0.0:
        raise ValueError("lidar_max_m must be positive")
    planner = np.zeros(7, dtype=np.float32)
    status = int(observation.planner_status)
    if 0 <= status < len(planner):
        planner[status] = 1.0
    lidar = np.clip(observation.lidar, 0.0, lidar_max_m).astype(np.float32) / lidar_max_m
    state = np.concatenate(
        (
            observation.goal_polar,
            observation.path_waypoints.reshape(-1),
            observation.robot_velocity,
            observation.base_action,
            observation.progress_history,
            observation.angular_velocity_history,
            planner,
            observation.failure_prediction.as_array(),
        ),
        dtype=np.float32,
    )
    if lidar.shape != (5, 180) or state.shape != (53,):
        raise ValueError(
            f"encoded observation has unexpected shapes lidar={lidar.shape}, state={state.shape}"
        )
    return lidar, state


class ONNXRecoveryPolicy:
    """Select only planning-valid recovery actions with a CPU ONNX model."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        lidar_max_m: float = 6.0,
        execution_provider: str = "CPUExecutionProvider",
        session: _InferenceSession | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.lidar_max_m = lidar_max_m
        if session is None:
            if not self.model_path.is_file():
                raise FileNotFoundError(f"recovery model does not exist: {self.model_path}")
            try:
                import onnxruntime as ort  # type: ignore[import-not-found]
            except ImportError as error:
                raise RuntimeError(
                    "onnxruntime is required for policy_type=bc; use the inference venv"
                ) from error
            available = ort.get_available_providers()
            if execution_provider not in available:
                raise RuntimeError(
                    f"ONNX provider {execution_provider!r} unavailable; available={available}"
                )
            session = ort.InferenceSession(
                str(self.model_path),
                providers=[execution_provider],
            )
        self._session = session
        input_names = {item.name for item in self._session.get_inputs()}
        expected_names = {"lidar", "state", "mask"}
        if input_names != expected_names:
            raise ValueError(
                f"ONNX model inputs must be {sorted(expected_names)}, got {sorted(input_names)}"
            )
        self.last_inference_latency_ms = 0.0

    def select_action(
        self,
        observation: RecoveryObservation,
        action_mask: npt.NDArray[np.bool_],
    ) -> RecoveryDecision:
        mask = np.asarray(action_mask, dtype=np.bool_)
        if mask.shape != (ACTION_COUNT,):
            raise ValueError(f"action mask must have shape ({ACTION_COUNT},)")
        if not bool(mask.any()):
            raise ValueError("action mask contains no legal action")
        lidar, state = encode_observation(observation, lidar_max_m=self.lidar_max_m)
        started = time.perf_counter()
        outputs = self._session.run(
            None,
            {
                "lidar": lidar[None],
                "state": state[None],
                "mask": mask[None],
            },
        )
        self.last_inference_latency_ms = (time.perf_counter() - started) * 1000.0
        if len(outputs) != 1:
            raise RuntimeError(f"ONNX policy returned {len(outputs)} outputs instead of one")
        logits = np.asarray(outputs[0], dtype=np.float32)
        if logits.shape != (1, ACTION_COUNT) or not np.all(np.isfinite(logits[0, mask])):
            raise RuntimeError(f"invalid ONNX policy output shape or values: {logits.shape}")
        action_id = int(np.argmax(logits[0]))
        if not mask[action_id]:
            raise RuntimeError(f"ONNX policy selected masked action {action_id}")
        legal_logits = logits[0, mask].astype(np.float64)
        legal_logits -= np.max(legal_logits)
        probabilities = np.exp(legal_logits)
        confidence = float(np.max(probabilities / np.sum(probabilities)))
        return RecoveryDecision(
            action_id=action_id,
            confidence=confidence,
            reason=(
                f"bc_onnx confidence={confidence:.3f} "
                f"latency_ms={self.last_inference_latency_ms:.3f}"
            ),
        )

    def reset(self) -> None:
        """Retain no temporal model state between recovery options."""
