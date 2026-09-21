#!/usr/bin/env bash
set -euo pipefail

runtime_root=/home/preface/PGRR-online
scenario_path=outputs/student/families_7_8_smoke/bottleneck_cross_flow_merge_medium_train_r00_s91610.json
episode_id=${RAMP_EPISODE_ID:-student_v78_bottleneck_cross_flow_merge_medium_train_r00_s91610_pgrr_function02}
model_path=/workspace/checkpoints/final/best.onnx
host_model_path=checkpoints/final/best.onnx
host_inference_python=.venv-inference/bin/python
expected_sha256=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2

cd "$runtime_root"

if ! docker version >/dev/null 2>&1; then
  echo 'ERROR: Docker client/server is unavailable.' >&2
  exit 20
fi
if [[ ! -f "$scenario_path" ]]; then
  echo "ERROR: scenario is missing: $scenario_path" >&2
  exit 21
fi
actual_sha256=$(sha256sum "$host_model_path" | awk '{print $1}')
if [[ "$actual_sha256" != "$expected_sha256" ]]; then
  echo "ERROR: checkpoint SHA-256 mismatch: $actual_sha256" >&2
  exit 22
fi
if [[ ! -x "$host_inference_python" ]]; then
  echo "ERROR: inference runtime is missing: $host_inference_python" >&2
  exit 23
fi

protected_outputs=(
  "data/raw/$episode_id.jsonl"
  "data/raw/$episode_id.metadata.json"
  "data/raw/$episode_id.outcome.json"
  "outputs/logs/baseline/${episode_id}_runtime.log"
  "outputs/logs/baseline/${episode_id}_status.log"
)
for output_path in "${protected_outputs[@]}"; do
  if [[ -e "$output_path" ]]; then
    echo "ERROR: refusing to overwrite existing function-smoke output: $output_path" >&2
    exit 24
  fi
done

RAMP_EPISODE_ID="$episode_id" \
RAMP_EPISODE_TIMEOUT_S=90 \
RAMP_SOURCE_POLICY=pgrr \
RAMP_BC_MODEL_PATH="$model_path" \
RAMP_CHECKPOINT_SHA256="$expected_sha256" \
SCENARIO="$scenario_path" \
scripts/arena/run_baseline_episode.sh

outcome_path="data/raw/$episode_id.outcome.json"
if [[ -f "$outcome_path" ]]; then
  printf '\nSaved outcome: %s\n' "$outcome_path"
  sed -n '1,120p' "$outcome_path"
fi
