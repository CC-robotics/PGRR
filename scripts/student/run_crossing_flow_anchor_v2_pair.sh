#!/usr/bin/env bash
set -euo pipefail

# Run the design-corrected <=15 m crossing-flow v2 pair.  This is a
# train-only screen, defaults to dry-run, and refuses to overwrite artifacts.

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
dry_run=${DRY_RUN:-1}
methods=${METHODS:-base,pgrr}
scenario_id=crossing_flow_medium_anchor_v2_train_r00_s95010
scenario_relative=outputs/student/advantage_scenario_screen_v2/generated/arena/map_empty/${scenario_id}.json
scenario_sha=5e230d5341a5e2ffbce025a0b970f1e23961b0f0749a7b98d0387431c3ee9e11
runtime_scenario_relative=outputs/student/advantage_scenario_screen_v2/scenarios/${scenario_id}.json
checkpoint_relative=checkpoints/dagger/coverage_safety_aligned/best.onnx
checkpoint_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2
result_relative=outputs/student/advantage_scenario_screen_v2/runtime

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

[[ "$dry_run" == 0 || "$dry_run" == 1 ]] || fail 'DRY_RUN must be 0 or 1'
[[ "$methods" == base || "$methods" == pgrr || "$methods" == base,pgrr ]] || \
  fail 'METHODS must be base, pgrr, or base,pgrr'
[[ -d "$runtime_root" ]] || fail "runtime root is missing: $runtime_root"
[[ -x "$runtime_root/scripts/arena/run_baseline_episode.sh" ]] || \
  fail 'Arena episode runner is missing'

source_scenario="$source_root/$scenario_relative"
runtime_scenario="$runtime_root/$runtime_scenario_relative"
[[ -f "$source_scenario" ]] || fail "source scenario is missing: $source_scenario"
actual_scenario_sha=$(sha256sum "$source_scenario" | awk '{print $1}')
[[ "$actual_scenario_sha" == "$scenario_sha" ]] || fail 'scenario SHA-256 mismatch'

checkpoint="$runtime_root/$checkpoint_relative"
[[ -f "$checkpoint" ]] || fail "PGRR checkpoint is missing: $checkpoint"
actual_checkpoint_sha=$(sha256sum "$checkpoint" | awk '{print $1}')
[[ "$actual_checkpoint_sha" == "$checkpoint_sha" ]] || fail 'checkpoint SHA-256 mismatch'

if [[ "$dry_run" == 0 ]]; then
  docker version >/dev/null 2>&1 || fail 'Docker client/server is unavailable'
fi

mkdir -p "$(dirname "$runtime_scenario")" "$source_root/$result_relative"
if [[ -f "$runtime_scenario" ]]; then
  runtime_sha=$(sha256sum "$runtime_scenario" | awk '{print $1}')
  [[ "$runtime_sha" == "$scenario_sha" ]] || fail 'runtime scenario differs from pinned input'
else
  cp "$source_scenario" "$runtime_scenario"
fi

IFS=',' read -r -a method_list <<< "$methods"
for method in "${method_list[@]}"; do
  episode_id="pgrr_advscreen_crossing_v2_train_s95010_${method}"
  protected=(
    "$runtime_root/data/raw/$episode_id.jsonl"
    "$runtime_root/data/raw/$episode_id.metadata.json"
    "$runtime_root/data/raw/$episode_id.outcome.json"
    "$runtime_root/outputs/logs/baseline/${episode_id}_runtime.log"
    "$runtime_root/outputs/logs/baseline/${episode_id}_status.log"
  )
  for output in "${protected[@]}"; do
    [[ ! -e "$output" ]] || fail "refusing to overwrite existing output: $output"
  done

  echo "READY method=$method episode=$episode_id scenario_sha=$scenario_sha"
  [[ "$dry_run" == 1 ]] && continue

  policy_args=(RAMP_SOURCE_POLICY=base)
  ros_domain_id=173
  if [[ "$method" == pgrr ]]; then
    policy_args=(
      RAMP_SOURCE_POLICY=pgrr
      RAMP_BC_MODEL_PATH=/workspace/$checkpoint_relative
      RAMP_CHECKPOINT_SHA256="$checkpoint_sha"
    )
    ros_domain_id=174
  fi
  (
    cd "$runtime_root"
    env \
      RAMP_EPISODE_ID="$episode_id" \
      RAMP_EPISODE_TIMEOUT_S=90 \
      RAMP_REPLICATE=0 \
      ROS_DOMAIN_ID="$ros_domain_id" \
      GZ_PARTITION="${episode_id}_gz" \
      IGN_PARTITION="${episode_id}_gz" \
      SCENARIO="$runtime_scenario_relative" \
      "${policy_args[@]}" \
      scripts/arena/run_baseline_episode.sh
  )

  for output in "${protected[@]}"; do
    if [[ -f "$output" ]]; then
      cp "$output" "$source_root/$result_relative/"
    fi
  done
done

echo "PAIR COMPLETE: dry_run=$dry_run methods=$methods scenario=$scenario_id"
