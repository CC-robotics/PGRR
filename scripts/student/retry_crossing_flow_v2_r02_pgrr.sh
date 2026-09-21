#!/usr/bin/env bash
set -euo pipefail

# Preserve the zero-sample INVALID_RESET and perform the single allowed retry
# for the same frozen r02 PGRR condition.

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
base_id=pgrr_advscreen_crossing_v2_train_r02_s95012_pgrr
retry_id=${base_id}_retry01
result_relative=outputs/student/advantage_scenario_screen_v2_replication/runtime
scenario_relative=outputs/student/advantage_scenario_screen_v2_replication/scenarios/crossing_flow_medium_anchor_v2_train_r02_s95012.json
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

original_outcome="$runtime_root/data/raw/${base_id}.outcome.json"
[[ -f "$original_outcome" ]] || fail 'original INVALID_RESET outcome is missing'
grep -q '"outcome": "INVALID_RESET"' "$original_outcome" || \
  fail 'retry is allowed only after INVALID_RESET'
grep -q '"sample_count": 0' "$original_outcome" || \
  fail 'original attempt was not a zero-sample infrastructure failure'

destination="$source_root/$result_relative"
mkdir -p "$destination"
original_artifacts=(
  "$runtime_root/data/raw/${base_id}.jsonl"
  "$runtime_root/data/raw/${base_id}.metadata.json"
  "$runtime_root/data/raw/${base_id}.outcome.json"
  "$runtime_root/outputs/logs/baseline/${base_id}_runtime.log"
  "$runtime_root/outputs/logs/baseline/${base_id}_status.log"
)
for artifact in "${original_artifacts[@]}"; do
  [[ ! -f "$artifact" ]] || cp "$artifact" "$destination/"
done

retry_artifacts=(
  "$runtime_root/data/raw/${retry_id}.jsonl"
  "$runtime_root/data/raw/${retry_id}.metadata.json"
  "$runtime_root/data/raw/${retry_id}.outcome.json"
  "$runtime_root/outputs/logs/baseline/${retry_id}_runtime.log"
  "$runtime_root/outputs/logs/baseline/${retry_id}_status.log"
)
for artifact in "${retry_artifacts[@]}"; do
  [[ ! -e "$artifact" ]] || fail "refusing to overwrite retry artifact: $artifact"
done

checkpoint="$runtime_root/$checkpoint_relative"
[[ "$(sha256sum "$checkpoint" | awk '{print $1}')" == "$checkpoint_sha" ]] || \
  fail 'checkpoint SHA-256 mismatch'
docker version >/dev/null 2>&1 || fail 'Docker client/server is unavailable'

set +e
(
  cd "$runtime_root"
  env \
    RAMP_EPISODE_ID="$retry_id" \
    RAMP_EPISODE_TIMEOUT_S=90 \
    RAMP_REPLICATE=2 \
    ROS_DOMAIN_ID=178 \
    GZ_PARTITION="${retry_id}_gz" \
    IGN_PARTITION="${retry_id}_gz" \
    SCENARIO="$scenario_relative" \
    RAMP_SOURCE_POLICY=pgrr \
    RAMP_BC_MODEL_PATH=/workspace/$checkpoint_relative \
    RAMP_CHECKPOINT_SHA256="$checkpoint_sha" \
    scripts/arena/run_baseline_episode.sh
)
run_status=$?
set -e

for artifact in "${retry_artifacts[@]}"; do
  [[ ! -f "$artifact" ]] || cp "$artifact" "$destination/"
done
exit "$run_status"
