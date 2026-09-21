#!/usr/bin/env bash
set -euo pipefail

# Run the two additional, predeclared train replicates for bounded closing-gap
# v3. The completed r00 pair is preserved and is not rerun.

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
dry_run=${DRY_RUN:-1}
replicates=${REPLICATES:-1,2}
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2
result_relative=outputs/student/closing_gap_bounded_v3_replication/runtime

fail() { echo "ERROR: $*" >&2; exit 2; }

[[ "$dry_run" == 0 || "$dry_run" == 1 ]] || fail 'DRY_RUN must be 0 or 1'
[[ "$replicates" == "1,2" || "$replicates" == "1" || "$replicates" == "2" ]] || \
  fail 'REPLICATES must be 1,2, 1, or 2'
[[ -x "$runtime_root/scripts/arena/run_baseline_episode.sh" ]] || fail 'Arena runner missing'
checkpoint="$runtime_root/$checkpoint_relative"
[[ -f "$checkpoint" ]] || fail 'checkpoint missing'
[[ "$(sha256sum "$checkpoint" | awk '{print $1}')" == "$checkpoint_sha" ]] || \
  fail 'checkpoint SHA-256 mismatch'
if [[ "$dry_run" == 0 ]]; then
  docker version >/dev/null 2>&1 || fail 'Docker client/server unavailable'
fi
mkdir -p "$source_root/$result_relative"

copy_outputs() {
  local episode_id=$1 path
  for path in \
    "$runtime_root/data/raw/$episode_id.jsonl" \
    "$runtime_root/data/raw/$episode_id.metadata.json" \
    "$runtime_root/data/raw/$episode_id.outcome.json" \
    "$runtime_root/outputs/logs/baseline/${episode_id}_runtime.log" \
    "$runtime_root/outputs/logs/baseline/${episode_id}_status.log"; do
    [[ ! -f "$path" ]] || cp "$path" "$source_root/$result_relative/"
  done
}

run_attempt() {
  local episode_id=$1 method=$2 replicate=$3 domain_id=$4 scenario_relative=$5
  local policy_args=(RAMP_SOURCE_POLICY=base)
  if [[ "$method" == pgrr ]]; then
    policy_args=(
      RAMP_SOURCE_POLICY=pgrr
      RAMP_BC_MODEL_PATH=/workspace/$checkpoint_relative
      RAMP_CHECKPOINT_SHA256="$checkpoint_sha"
    )
  fi
  local path
  for path in \
    "$runtime_root/data/raw/$episode_id.jsonl" \
    "$runtime_root/data/raw/$episode_id.metadata.json" \
    "$runtime_root/data/raw/$episode_id.outcome.json" \
    "$runtime_root/outputs/logs/baseline/${episode_id}_runtime.log" \
    "$runtime_root/outputs/logs/baseline/${episode_id}_status.log"; do
    [[ ! -e "$path" ]] || fail "refusing to overwrite $path"
  done
  echo "READY replicate=$replicate method=$method episode=$episode_id"
  [[ "$dry_run" == 1 ]] && return 0
  local status=0
  if ! (
    cd "$runtime_root"
    env \
      RAMP_EPISODE_ID="$episode_id" \
      RAMP_EPISODE_TIMEOUT_S=90 \
      RAMP_REPLICATE="$replicate" \
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

run_replicate() {
  local replicate=$1 seed=$2 source_directory=$3 scenario_id=$4 scenario_sha=$5 first_domain=$6
  local source_relative="$source_directory/generated/arena/map_empty/${scenario_id}.json"
  local scenario_relative="outputs/student/closing_gap_bounded_v3_replication/scenarios/${scenario_id}.json"
  local source_scenario="$source_root/$source_relative"
  local runtime_scenario="$runtime_root/$scenario_relative"
  [[ -f "$source_scenario" ]] || fail "source scenario missing: $source_scenario"
  [[ "$(sha256sum "$source_scenario" | awk '{print $1}')" == "$scenario_sha" ]] || \
    fail "$scenario_id source SHA-256 mismatch"
  mkdir -p "$(dirname "$runtime_scenario")"
  if [[ -f "$runtime_scenario" ]]; then
    [[ "$(sha256sum "$runtime_scenario" | awk '{print $1}')" == "$scenario_sha" ]] || \
      fail "$scenario_id runtime copy differs"
  else
    cp "$source_scenario" "$runtime_scenario"
  fi

  local method domain episode outcome retry
  for method in base pgrr; do
    domain=$first_domain
    [[ "$method" == pgrr ]] && domain=$((first_domain + 1))
    episode="pgrr_priority_closinggap_v3_train_r0${replicate}_s${seed}_${method}"
    run_attempt "$episode" "$method" "$replicate" "$domain" "$scenario_relative"
    [[ "$dry_run" == 1 ]] && continue
    outcome="$runtime_root/data/raw/$episode.outcome.json"
    if python3 -c 'import json,sys; raise SystemExit(0 if json.load(open(sys.argv[1]))["outcome"] in {"SIMULATOR_FAILURE", "INVALID_RESET"} else 1)' "$outcome"; then
      retry="${episode}_retry01"
      run_attempt "$retry" "$method" "$replicate" "$((domain + 20))" "$scenario_relative"
    fi
  done
}

if [[ "$replicates" == "1,2" || "$replicates" == "1" ]]; then
  run_replicate 1 98201 \
    outputs/student/closing_gap_bounded_v3_train_r01 \
    closing_gap_bounded_release_v3_train_r01_s98201 \
    3b2bba3081897a9b82e4fd6b8e1885cb850c4cbc9bdd1f5fb45a061c4038bd24 \
    231
fi
if [[ "$replicates" == "1,2" || "$replicates" == "2" ]]; then
  run_replicate 2 98202 \
    outputs/student/closing_gap_bounded_v3_train_r02 \
    closing_gap_bounded_release_v3_train_r02_s98202 \
    84e8fbdc28f005166ea8ab867dfde947ae335f834c348de499ea089e7aa283ba \
    225
fi

echo "CLOSING-GAP V3 TRAIN REPLICATION COMPLETE: dry_run=$dry_run additional_pairs=2"
