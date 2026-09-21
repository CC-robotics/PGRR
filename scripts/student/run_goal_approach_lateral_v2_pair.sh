#!/usr/bin/env bash
set -euo pipefail

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
dry_run=${DRY_RUN:-1}
scenario_id=goal_approach_lateral_one_shot_v2_train_r00_s97100
scenario_source_relative=outputs/student/goal_approach_lateral_v2_screen/generated/arena/map_empty/${scenario_id}.json
scenario_runtime_relative=outputs/student/goal_approach_lateral_v2_screen/scenarios/${scenario_id}.json
scenario_sha=7587703a8484d02f46138975f815fd5d99f6a92ff8edb479b8a74edd7613c1f7
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2
result_relative=outputs/student/goal_approach_lateral_v2_screen/runtime

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

[[ "$dry_run" == 0 || "$dry_run" == 1 ]] || fail 'DRY_RUN must be 0 or 1'
[[ -x "$runtime_root/scripts/arena/run_baseline_episode.sh" ]] || fail 'Arena runner missing'
source_scenario="$source_root/$scenario_source_relative"
runtime_scenario="$runtime_root/$scenario_runtime_relative"
checkpoint="$runtime_root/$checkpoint_relative"
[[ -f "$source_scenario" ]] || fail 'source scenario missing'
[[ "$(sha256sum "$source_scenario" | awk '{print $1}')" == "$scenario_sha" ]] || \
  fail 'source scenario SHA-256 mismatch'
[[ -f "$checkpoint" ]] || fail 'checkpoint missing'
[[ "$(sha256sum "$checkpoint" | awk '{print $1}')" == "$checkpoint_sha" ]] || \
  fail 'checkpoint SHA-256 mismatch'
if [[ "$dry_run" == 0 ]]; then
  docker version >/dev/null 2>&1 || fail 'Docker client/server unavailable'
fi
mkdir -p "$(dirname "$runtime_scenario")" "$source_root/$result_relative"
if [[ -f "$runtime_scenario" ]]; then
  [[ "$(sha256sum "$runtime_scenario" | awk '{print $1}')" == "$scenario_sha" ]] || \
    fail 'runtime scenario copy differs'
else
  cp "$source_scenario" "$runtime_scenario"
fi

run_method() {
  local method=$1
  local domain_id=$2
  local episode_id="pgrr_priority_goalapproach_v2_train_s97100_${method}"
  local policy_args=(RAMP_SOURCE_POLICY=base)
  if [[ "$method" == pgrr ]]; then
    policy_args=(
      RAMP_SOURCE_POLICY=pgrr
      RAMP_BC_MODEL_PATH=/workspace/$checkpoint_relative
      RAMP_CHECKPOINT_SHA256="$checkpoint_sha"
    )
  fi
  local outputs=(
    "$runtime_root/data/raw/$episode_id.jsonl"
    "$runtime_root/data/raw/$episode_id.metadata.json"
    "$runtime_root/data/raw/$episode_id.outcome.json"
    "$runtime_root/outputs/logs/baseline/${episode_id}_runtime.log"
    "$runtime_root/outputs/logs/baseline/${episode_id}_status.log"
  )
  for output in "${outputs[@]}"; do
    [[ ! -e "$output" ]] || fail "refusing to overwrite $output"
  done
  echo "READY method=$method episode=$episode_id"
  [[ "$dry_run" == 1 ]] && return 0
  (
    cd "$runtime_root"
    env \
      RAMP_EPISODE_ID="$episode_id" \
      RAMP_EPISODE_TIMEOUT_S=90 \
      RAMP_REPLICATE=0 \
      RAMP_ENABLE_EVENT_CONTROL=1 \
      ROS_DOMAIN_ID="$domain_id" \
      GZ_PARTITION="${episode_id}_gz" \
      IGN_PARTITION="${episode_id}_gz" \
      SCENARIO="$scenario_runtime_relative" \
      "${policy_args[@]}" \
      scripts/arena/run_baseline_episode.sh
  )
  for output in "${outputs[@]}"; do
    [[ ! -f "$output" ]] || cp "$output" "$source_root/$result_relative/"
  done
}

run_method base 191
run_method pgrr 192
echo "GOAL-APPROACH V2 PAIR COMPLETE: dry_run=$dry_run"
