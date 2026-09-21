#!/usr/bin/env bash
set -euo pipefail

# Preserve the zero-sample Base infrastructure failure, then perform the sole
# same-seed Base retry and the not-yet-attempted PGRR half of the fixed pair.

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
scenario_relative=outputs/student/goal_approach_lateral_v2_screen/scenarios/goal_approach_lateral_one_shot_v2_train_r00_s97100.json
scenario_sha=7587703a8484d02f46138975f815fd5d99f6a92ff8edb479b8a74edd7613c1f7
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2
result_root="$source_root/outputs/student/goal_approach_lateral_v2_screen/runtime"
failed_id=pgrr_priority_goalapproach_v2_train_s97100_base

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

scenario="$runtime_root/$scenario_relative"
checkpoint="$runtime_root/$checkpoint_relative"
outcome="$runtime_root/data/raw/$failed_id.outcome.json"
[[ -f "$scenario" ]] || fail 'runtime scenario missing'
[[ "$(sha256sum "$scenario" | awk '{print $1}')" == "$scenario_sha" ]] || fail 'scenario hash mismatch'
[[ -f "$checkpoint" ]] || fail 'checkpoint missing'
[[ "$(sha256sum "$checkpoint" | awk '{print $1}')" == "$checkpoint_sha" ]] || fail 'checkpoint hash mismatch'
[[ -f "$outcome" ]] || fail 'original Base failure outcome missing'
python3 - "$outcome" <<'PY'
import json, sys
value = json.load(open(sys.argv[1]))
assert value["outcome"] == "SIMULATOR_FAILURE"
assert value["sample_count"] == 0
PY
docker version >/dev/null 2>&1 || fail 'Docker client/server unavailable'
mkdir -p "$result_root"

copy_outputs() {
  local episode_id=$1
  for path in \
    "$runtime_root/data/raw/$episode_id.jsonl" \
    "$runtime_root/data/raw/$episode_id.metadata.json" \
    "$runtime_root/data/raw/$episode_id.outcome.json" \
    "$runtime_root/outputs/logs/baseline/${episode_id}_runtime.log" \
    "$runtime_root/outputs/logs/baseline/${episode_id}_status.log"; do
    [[ ! -f "$path" ]] || cp "$path" "$result_root/"
  done
}

copy_outputs "$failed_id"

run_attempt() {
  local episode_id=$1
  local method=$2
  local domain_id=$3
  local policy_args=(RAMP_SOURCE_POLICY=base)
  if [[ "$method" == pgrr ]]; then
    policy_args=(
      RAMP_SOURCE_POLICY=pgrr
      RAMP_BC_MODEL_PATH=/workspace/$checkpoint_relative
      RAMP_CHECKPOINT_SHA256="$checkpoint_sha"
    )
  fi
  for path in \
    "$runtime_root/data/raw/$episode_id.jsonl" \
    "$runtime_root/data/raw/$episode_id.metadata.json" \
    "$runtime_root/data/raw/$episode_id.outcome.json" \
    "$runtime_root/outputs/logs/baseline/${episode_id}_runtime.log" \
    "$runtime_root/outputs/logs/baseline/${episode_id}_status.log"; do
    [[ ! -e "$path" ]] || fail "refusing to overwrite $path"
  done
  local status=0
  if ! (
    cd "$runtime_root"
    env \
      RAMP_EPISODE_ID="$episode_id" \
      RAMP_EPISODE_TIMEOUT_S=90 \
      RAMP_REPLICATE=0 \
      RAMP_ENABLE_EVENT_CONTROL=1 \
      ROS_DOMAIN_ID="$domain_id" \
      GZ_PARTITION="${episode_id}_gz" \
      IGN_PARTITION="${episode_id}_gz" \
      SCENARIO="$scenario_relative" \
      "${policy_args[@]}" \
      scripts/arena/run_baseline_episode.sh
  ); then
    status=$?
  fi
  copy_outputs "$episode_id"
  [[ -f "$runtime_root/data/raw/$episode_id.outcome.json" ]] || \
    fail "attempt produced no outcome: $episode_id"
  echo "ATTEMPT COMPLETE episode=$episode_id runner_status=$status"
}

run_attempt "${failed_id}_retry01" base 211
run_attempt pgrr_priority_goalapproach_v2_train_s97100_pgrr pgrr 212
