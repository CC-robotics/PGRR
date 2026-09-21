#!/usr/bin/env bash
set -euo pipefail

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
dry_run=${DRY_RUN:-1}
start_replicate=${START_REPLICATE:-0}
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2
result_relative=outputs/student/goal_approach_lateral_v2_validation/runtime

fail() { echo "ERROR: $*" >&2; exit 2; }
[[ "$dry_run" == 0 || "$dry_run" == 1 ]] || fail 'DRY_RUN must be 0 or 1'
[[ "$start_replicate" =~ ^[0-2]$ ]] || fail 'START_REPLICATE must be 0, 1, or 2'
[[ -x "$runtime_root/scripts/arena/run_baseline_episode.sh" ]] || fail 'Arena runner missing'
checkpoint="$runtime_root/$checkpoint_relative"
[[ -f "$checkpoint" ]] || fail 'checkpoint missing'
[[ "$(sha256sum "$checkpoint" | awk '{print $1}')" == "$checkpoint_sha" ]] || fail 'checkpoint hash mismatch'
[[ "$dry_run" == 1 ]] || docker version >/dev/null 2>&1 || fail 'Docker unavailable'
mkdir -p "$source_root/$result_relative"

copy_outputs() {
  local episode=$1 path
  for path in \
    "$runtime_root/data/raw/$episode.jsonl" \
    "$runtime_root/data/raw/$episode.metadata.json" \
    "$runtime_root/data/raw/$episode.outcome.json" \
    "$runtime_root/outputs/logs/baseline/${episode}_runtime.log" \
    "$runtime_root/outputs/logs/baseline/${episode}_status.log"; do
    [[ ! -f "$path" ]] || cp "$path" "$source_root/$result_relative/"
  done
}

run_attempt() {
  local episode=$1 method=$2 replicate=$3 domain=$4 scenario=$5 path status=0
  local policy=(RAMP_SOURCE_POLICY=base)
  if [[ "$method" == pgrr ]]; then
    policy=(RAMP_SOURCE_POLICY=pgrr RAMP_BC_MODEL_PATH=/workspace/$checkpoint_relative RAMP_CHECKPOINT_SHA256="$checkpoint_sha")
  fi
  for path in \
    "$runtime_root/data/raw/$episode.jsonl" \
    "$runtime_root/data/raw/$episode.metadata.json" \
    "$runtime_root/data/raw/$episode.outcome.json" \
    "$runtime_root/outputs/logs/baseline/${episode}_runtime.log" \
    "$runtime_root/outputs/logs/baseline/${episode}_status.log"; do
    [[ ! -e "$path" ]] || fail "refusing to overwrite $path"
  done
  echo "READY replicate=$replicate method=$method episode=$episode"
  [[ "$dry_run" == 1 ]] && return 0
  if ! (
    cd "$runtime_root"
    env RAMP_EPISODE_ID="$episode" RAMP_EPISODE_TIMEOUT_S=90 \
      RAMP_REPLICATE="$replicate" RAMP_ENABLE_EVENT_CONTROL=1 \
      ROS_DOMAIN_ID="$domain" GZ_PARTITION="${episode}_gz" IGN_PARTITION="${episode}_gz" \
      SCENARIO="$scenario" "${policy[@]}" scripts/arena/run_baseline_episode.sh
  ); then status=$?; fi
  copy_outputs "$episode"
  local outcome_file="$runtime_root/data/raw/$episode.outcome.json"
  [[ -f "$outcome_file" ]] || fail "no outcome: $episode"
  local outcome
  outcome=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["outcome"])' "$outcome_file")
  echo "ATTEMPT COMPLETE episode=$episode outcome=$outcome runner_status=$status"
  [[ "$outcome" != SIMULATOR_FAILURE && "$outcome" != INVALID_RESET ]] || return 10
}

run_method() {
  local episode=$1 method=$2 replicate=$3 domain=$4 scenario=$5 status
  if run_attempt "$episode" "$method" "$replicate" "$domain" "$scenario"; then return 0; else status=$?; fi
  [[ "$status" == 10 ]] || return "$status"
  echo "INFRASTRUCTURE RETRY authorized episode=${episode}_retry01"
  run_attempt "${episode}_retry01" "$method" "$replicate" "$((domain + 20))" "$scenario" || true
}

run_replicate() {
  local replicate=$1 seed=$2 scenario_id=$3 source_dir=$4 expected_sha=$5 domain=$6
  local source_rel="$source_dir/generated/arena/map_empty/${scenario_id}.json"
  local runtime_rel="outputs/student/goal_approach_lateral_v2_validation/scenarios/${scenario_id}.json"
  local source="$source_root/$source_rel" runtime="$runtime_root/$runtime_rel"
  [[ -f "$source" ]] || fail "source scenario missing: $source"
  [[ "$(sha256sum "$source" | awk '{print $1}')" == "$expected_sha" ]] || fail 'scenario hash mismatch'
  mkdir -p "$(dirname "$runtime")"
  if [[ -f "$runtime" ]]; then
    [[ "$(sha256sum "$runtime" | awk '{print $1}')" == "$expected_sha" ]] || fail 'runtime copy differs'
  else cp "$source" "$runtime"; fi
  local prefix="pgrr_priority_goalapproach_v2_validation_r0${replicate}_s${seed}"
  run_method "${prefix}_base" base "$replicate" "$domain" "$runtime_rel"
  run_method "${prefix}_pgrr" pgrr "$replicate" "$((domain + 1))" "$runtime_rel"
}

if (( start_replicate <= 0 )); then
  run_replicate 0 98100 goal_approach_lateral_one_shot_v2_validation_r00_s98100 outputs/student/goal_approach_lateral_v2_validation_r00 3efd477c2fc44543bdc2846aebc5d404d0d4fdadc5596b3dbc0c5b2d102e0d2d 231
fi
if (( start_replicate <= 1 )); then
  run_replicate 1 98101 goal_approach_lateral_one_shot_v2_validation_r01_s98101 outputs/student/goal_approach_lateral_v2_validation_r01 f0a41c37f2a18fe0ce9cf6b0c8549353dab757ac9d5186e98bb89b481316f2de 225
fi
if (( start_replicate <= 2 )); then
  run_replicate 2 98102 goal_approach_lateral_one_shot_v2_validation_r02_s98102 outputs/student/goal_approach_lateral_v2_validation_r02 eec32e194a874ad01be8001baa075ba8a03d26c96c7b63617e0cd93098e06d34 227
fi
echo "GOAL-APPROACH V2 VALIDATION COMPLETE: dry_run=$dry_run pairs=3"
