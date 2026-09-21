#!/usr/bin/env bash
set -euo pipefail

# Execute the two predeclared additional train replicates for the frozen 15 m
# crossing-flow v2 design. r00 is already complete and is not rerun here.

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
dry_run=${DRY_RUN:-1}
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2
result_relative=outputs/student/advantage_scenario_screen_v2_replication/runtime

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

run_replicate() {
  local replicate=$1
  local seed=$2
  local scenario_id=$3
  local source_directory=$4
  local scenario_sha=$5
  local base_domain=$6
  local source_relative="$source_directory/generated/arena/map_empty/${scenario_id}.json"
  local runtime_relative="outputs/student/advantage_scenario_screen_v2_replication/scenarios/${scenario_id}.json"
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

  for method in base pgrr; do
    local episode_id="pgrr_advscreen_crossing_v2_train_r0${replicate}_s${seed}_${method}"
    local domain_id=$base_domain
    local policy_args=(RAMP_SOURCE_POLICY=base)
    if [[ "$method" == pgrr ]]; then
      domain_id=$((base_domain + 1))
      policy_args=(
        RAMP_SOURCE_POLICY=pgrr
        RAMP_BC_MODEL_PATH=/workspace/$checkpoint_relative
        RAMP_CHECKPOINT_SHA256="$checkpoint_sha"
      )
    fi
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
    echo "READY replicate=$replicate seed=$seed method=$method episode=$episode_id"
    [[ "$dry_run" == 1 ]] && continue
    (
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
    )
    for output in "${protected[@]}"; do
      [[ ! -f "$output" ]] || cp "$output" "$source_root/$result_relative/"
    done
  done
}

run_replicate 1 95011 \
  crossing_flow_medium_anchor_v2_train_r01_s95011 \
  outputs/student/advantage_scenario_screen_v2_r01 \
  ffdb8f9d5907c7c1a0209c8fecdd587a5bf3b3b9ea4da379fbe96054c23a93a1 \
  175
run_replicate 2 95012 \
  crossing_flow_medium_anchor_v2_train_r02_s95012 \
  outputs/student/advantage_scenario_screen_v2_r02 \
  8ee5835efabeb48d94a6b10b9a7941f01110d6466a25e0dcf1fbf9ac15819f3a \
  177

echo "TRAIN REPLICATION COMPLETE: dry_run=$dry_run additional_pairs=2"
