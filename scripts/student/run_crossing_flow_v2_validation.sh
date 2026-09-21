#!/usr/bin/env bash
set -euo pipefail

# Run the three predeclared independent-validation pairs for the frozen 15 m
# crossing-flow v2 design. Every attempt is preserved. Only zero-performance
# infrastructure outcomes may receive one same-seed retry.

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
dry_run=${DRY_RUN:-1}
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2
result_relative=outputs/student/advantage_scenario_screen_v2_validation/runtime

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

[[ "$dry_run" == 0 || "$dry_run" == 1 ]] || fail 'DRY_RUN must be 0 or 1'
[[ -x "$runtime_root/scripts/arena/run_baseline_episode.sh" ]] || \
  fail 'Arena episode runner is missing'
checkpoint="$runtime_root/$checkpoint_relative"
[[ -f "$checkpoint" ]] || fail "PGRR checkpoint is missing: $checkpoint"
[[ "$(sha256sum "$checkpoint" | awk '{print $1}')" == "$checkpoint_sha" ]] || \
  fail 'checkpoint SHA-256 mismatch'
if [[ "$dry_run" == 0 ]]; then
  docker version >/dev/null 2>&1 || fail 'Docker client/server is unavailable'
fi
mkdir -p "$source_root/$result_relative"

copy_attempt() {
  local episode_id=$1
  local files=(
    "$runtime_root/data/raw/$episode_id.jsonl"
    "$runtime_root/data/raw/$episode_id.metadata.json"
    "$runtime_root/data/raw/$episode_id.outcome.json"
    "$runtime_root/outputs/logs/baseline/${episode_id}_runtime.log"
    "$runtime_root/outputs/logs/baseline/${episode_id}_status.log"
  )
  for file in "${files[@]}"; do
    [[ ! -f "$file" ]] || cp "$file" "$source_root/$result_relative/"
  done
}

run_attempt() {
  local episode_id=$1
  local method=$2
  local replicate=$3
  local domain_id=$4
  local runtime_relative=$5
  local protected=(
    "$runtime_root/data/raw/$episode_id.jsonl"
    "$runtime_root/data/raw/$episode_id.metadata.json"
    "$runtime_root/data/raw/$episode_id.outcome.json"
    "$runtime_root/outputs/logs/baseline/${episode_id}_runtime.log"
    "$runtime_root/outputs/logs/baseline/${episode_id}_status.log"
  )
  for output in "${protected[@]}"; do
    [[ ! -e "$output" ]] || fail "refusing to overwrite existing output: $output"
  done
  local policy_args=(RAMP_SOURCE_POLICY=base)
  if [[ "$method" == pgrr ]]; then
    policy_args=(
      RAMP_SOURCE_POLICY=pgrr
      RAMP_BC_MODEL_PATH=/workspace/$checkpoint_relative
      RAMP_CHECKPOINT_SHA256="$checkpoint_sha"
    )
  fi
  echo "READY replicate=$replicate method=$method episode=$episode_id"
  [[ "$dry_run" == 1 ]] && return 0
  local run_status=0
  if ! (
    cd "$runtime_root"
    env \
      RAMP_EPISODE_ID="$episode_id" \
      RAMP_EPISODE_TIMEOUT_S=90 \
      RAMP_REPLICATE="$replicate" \
      ROS_DOMAIN_ID="$domain_id" \
      GZ_PARTITION="${episode_id}_gz" \
      IGN_PARTITION="${episode_id}_gz" \
      SCENARIO="$runtime_relative" \
      "${policy_args[@]}" \
      scripts/arena/run_baseline_episode.sh
  ); then
    run_status=$?
  fi
  copy_attempt "$episode_id"
  local outcome_file="$runtime_root/data/raw/$episode_id.outcome.json"
  [[ -f "$outcome_file" ]] || fail "attempt produced no outcome sidecar: $episode_id"
  local outcome
  outcome=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["outcome"])' "$outcome_file")
  echo "ATTEMPT COMPLETE episode=$episode_id outcome=$outcome runner_status=$run_status"
  if [[ "$outcome" == INVALID_RESET || "$outcome" == SIMULATOR_FAILURE ]]; then
    return 10
  fi
  return 0
}

run_method() {
  local stem=$1
  local method=$2
  local replicate=$3
  local domain_id=$4
  local runtime_relative=$5
  if run_attempt "$stem" "$method" "$replicate" "$domain_id" "$runtime_relative"; then
    return 0
  else
    local status=$?
    [[ "$status" == 10 ]] || return "$status"
  fi
  echo "INFRASTRUCTURE RETRY authorized episode=${stem}_retry01"
  run_attempt "${stem}_retry01" "$method" "$replicate" "$((domain_id + 20))" \
    "$runtime_relative" || true
}

run_replicate() {
  local replicate=$1
  local seed=$2
  local scenario_id=$3
  local source_directory=$4
  local scenario_sha=$5
  local base_domain=$6
  local source_relative="$source_directory/generated/arena/map_empty/${scenario_id}.json"
  local runtime_relative="outputs/student/advantage_scenario_screen_v2_validation/scenarios/${scenario_id}.json"
  local source_scenario="$source_root/$source_relative"
  local runtime_scenario="$runtime_root/$runtime_relative"

  [[ -f "$source_scenario" ]] || fail "source scenario is missing: $source_scenario"
  [[ "$(sha256sum "$source_scenario" | awk '{print $1}')" == "$scenario_sha" ]] || \
    fail "$scenario_id source SHA-256 mismatch"
  mkdir -p "$(dirname "$runtime_scenario")"
  if [[ -f "$runtime_scenario" ]]; then
    [[ "$(sha256sum "$runtime_scenario" | awk '{print $1}')" == "$scenario_sha" ]] || \
      fail "$scenario_id runtime copy differs"
  else
    cp "$source_scenario" "$runtime_scenario"
  fi

  local prefix="pgrr_advscreen_crossing_v2_validation_r0${replicate}_s${seed}"
  run_method "${prefix}_base" base "$replicate" "$base_domain" "$runtime_relative"
  run_method "${prefix}_pgrr" pgrr "$replicate" "$((base_domain + 1))" "$runtime_relative"
}

run_replicate 0 96000 \
  crossing_flow_medium_anchor_v2_validation_r00_s96000 \
  outputs/student/advantage_scenario_screen_v2_validation_r00 \
  c690889d213a1d7a3d4e7d24b994a0bcd63999b0d8db071688d88fb90aa2897a \
  181
run_replicate 1 96001 \
  crossing_flow_medium_anchor_v2_validation_r01_s96001 \
  outputs/student/advantage_scenario_screen_v2_validation_r01 \
  a1b73b3dab172127add66a687974a0da10498cca047ce0564ce677c488f2e11c \
  183
run_replicate 2 96002 \
  crossing_flow_medium_anchor_v2_validation_r02_s96002 \
  outputs/student/advantage_scenario_screen_v2_validation_r02 \
  0c9ee5eec2463ab5af4e8098263ccf5027d27de7cc5d1a44d2adb9f29a23d7e2 \
  185

echo "VALIDATION COMPLETE: dry_run=$dry_run pairs=3"
