#!/usr/bin/env bash
set -euo pipefail

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
dry_run=${DRY_RUN:-1}
scenario_id=${SCENARIO_ID:-closing_gap_bounded_release_v2_train_r00_s98200}
source_relative=${SOURCE_RELATIVE:-outputs/student/closing_gap_bounded_v2_screen/generated/arena/map_empty/${scenario_id}.json}
runtime_relative=${RUNTIME_RELATIVE:-outputs/student/closing_gap_bounded_v2_screen/scenarios/${scenario_id}.json}
scenario_sha=${SCENARIO_SHA:-25790b2aa32fe2971663e158b97d1e8b03fa78bad87ee1d7a9fbbb8bf5e2cf3b}
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2
result_relative=${RESULT_RELATIVE:-outputs/student/closing_gap_bounded_v2_screen/runtime}
episode_prefix=${EPISODE_PREFIX:-pgrr_priority_closinggap_v2_train_s98200}

fail() { echo "ERROR: $*" >&2; exit 2; }
[[ "$dry_run" == 0 || "$dry_run" == 1 ]] || fail 'DRY_RUN must be 0 or 1'
[[ -x "$runtime_root/scripts/arena/run_baseline_episode.sh" ]] || fail 'Arena runner missing'
source_scenario="$source_root/$source_relative"
runtime_scenario="$runtime_root/$runtime_relative"
checkpoint="$runtime_root/$checkpoint_relative"
[[ -f "$source_scenario" ]] || fail 'source scenario missing'
[[ "$(sha256sum "$source_scenario" | awk '{print $1}')" == "$scenario_sha" ]] || fail 'scenario hash mismatch'
[[ -f "$checkpoint" ]] || fail 'checkpoint missing'
[[ "$(sha256sum "$checkpoint" | awk '{print $1}')" == "$checkpoint_sha" ]] || fail 'checkpoint hash mismatch'
[[ "$dry_run" == 1 ]] || docker version >/dev/null 2>&1 || fail 'Docker unavailable'
mkdir -p "$(dirname "$runtime_scenario")" "$source_root/$result_relative"
if [[ -f "$runtime_scenario" ]]; then
  [[ "$(sha256sum "$runtime_scenario" | awk '{print $1}')" == "$scenario_sha" ]] || fail 'runtime copy differs'
else cp "$source_scenario" "$runtime_scenario"; fi

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
  local episode=$1 method=$2 domain=$3 path status=0
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
  echo "READY method=$method episode=$episode"
  [[ "$dry_run" == 1 ]] && return 0
  if ! (
    cd "$runtime_root"
    env RAMP_EPISODE_ID="$episode" RAMP_EPISODE_TIMEOUT_S=90 RAMP_REPLICATE=0 \
      RAMP_ENABLE_EVENT_CONTROL=1 ROS_DOMAIN_ID="$domain" \
      GZ_PARTITION="${episode}_gz" IGN_PARTITION="${episode}_gz" \
      SCENARIO="$runtime_relative" "${policy[@]}" scripts/arena/run_baseline_episode.sh
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
  local episode=$1 method=$2 domain=$3 status
  if run_attempt "$episode" "$method" "$domain"; then return 0; else status=$?; fi
  [[ "$status" == 10 ]] || return "$status"
  echo "INFRASTRUCTURE RETRY authorized episode=${episode}_retry01"
  run_attempt "${episode}_retry01" "$method" "$((domain - 10))" || true
}

run_method "${episode_prefix}_base" base 229
run_method "${episode_prefix}_pgrr" pgrr 230
echo "CLOSING-GAP V2 PAIR COMPLETE: dry_run=$dry_run"
