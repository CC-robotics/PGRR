#!/usr/bin/env bash
set -euo pipefail

runtime_root=${RUNTIME_ROOT:-/home/preface/PGRR-online}
source_root=${SOURCE_ROOT:-'/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR'}
plan_relative=outputs/student/eight_family_pilot/minimal_pair_plan.tsv
plan_path="$source_root/$plan_relative"
dry_run=${DRY_RUN:-1}
methods=${METHODS:-base,pgrr}
start_at=${START_AT:-0}
limit=${LIMIT:-0}
retry_suffix=${RETRY_SUFFIX:-}
expected_model_sha=78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2

fail() {
  echo "ERROR: $*" >&2
  exit 2
}

[[ "$dry_run" == 0 || "$dry_run" == 1 ]] || fail 'DRY_RUN must be 0 or 1'
[[ "$start_at" =~ ^[0-9]+$ ]] || fail 'START_AT must be a non-negative integer'
[[ "$limit" =~ ^[0-9]+$ ]] || fail 'LIMIT must be a non-negative integer'
[[ -z "$retry_suffix" || "$retry_suffix" =~ ^_retry[0-9][0-9]$ ]] || \
  fail 'RETRY_SUFFIX must be empty or match _retryNN'
[[ -d "$runtime_root" ]] || fail "runtime root is missing: $runtime_root"
[[ -f "$plan_path" ]] || fail "pinned plan is missing: $plan_path"
[[ -x "$runtime_root/scripts/arena/run_baseline_episode.sh" ]] || fail 'Arena episode runner is missing'

case ",$methods," in
  *,base,*|*,pgrr,*) ;;
  *) fail 'METHODS must contain base and/or pgrr' ;;
esac
if [[ ",$methods," == *,pgrr,* ]]; then
  [[ -x "$runtime_root/.venv-inference/bin/python" ]] || fail 'PGRR inference Python is missing'
  model_path="$runtime_root/checkpoints/dagger/coverage_safety_aligned/best.onnx"
  [[ -f "$model_path" ]] || fail "PGRR checkpoint is missing: $model_path"
  actual_model_sha=$(sha256sum "$model_path" | awk '{print $1}')
  [[ "$actual_model_sha" == "$expected_model_sha" ]] || fail 'PGRR checkpoint SHA-256 mismatch'
fi
if [[ "$dry_run" == 0 ]]; then
  docker version >/dev/null 2>&1 || fail 'Docker client/server is unavailable'
fi

mkdir -p "$runtime_root/outputs/student/eight_family_pilot/scenarios"
selected=0
checked=0
while IFS=$'\t' read -r order family_index family method episode_id scenario_id \
  scenario_path scenario_sha runtime_scenario seed timeout_s ros_domain_id; do
  ros_domain_id=${ros_domain_id%$'\r'}
  [[ "$order" == order ]] && continue
  ((order >= start_at)) || continue
  [[ ",$methods," == *",$method,"* ]] || continue
  if ((limit > 0 && selected >= limit)); then
    break
  fi

  episode_id="${episode_id}${retry_suffix}"
  source_scenario="$source_root/$scenario_path"
  destination="$runtime_root/$runtime_scenario"
  [[ -f "$source_scenario" ]] || fail "$episode_id source scenario missing"
  actual_scenario_sha=$(sha256sum "$source_scenario" | awk '{print $1}')
  [[ "$actual_scenario_sha" == "$scenario_sha" ]] || fail "$episode_id source scenario hash mismatch"
  if [[ -f "$destination" ]]; then
    destination_sha=$(sha256sum "$destination" | awk '{print $1}')
    [[ "$destination_sha" == "$scenario_sha" ]] || fail "$episode_id runtime scenario differs"
  else
    cp "$source_scenario" "$destination"
  fi

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

  printf 'READY order=%s family=%s method=%s episode=%s seed=%s domain=%s\n' \
    "$order" "$family" "$method" "$episode_id" "$seed" "$ros_domain_id"
  ((selected += 1))
  ((checked += 1))
  [[ "$dry_run" == 1 ]] && continue

  policy_args=()
  if [[ "$method" == pgrr ]]; then
    policy_args=(
      RAMP_SOURCE_POLICY=pgrr
      RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx
      RAMP_CHECKPOINT_SHA256="$expected_model_sha"
    )
  else
    policy_args=(RAMP_SOURCE_POLICY=base)
  fi
  (
    cd "$runtime_root"
    env \
      RAMP_EPISODE_ID="$episode_id" \
      RAMP_EPISODE_TIMEOUT_S="$timeout_s" \
      RAMP_REPLICATE=0 \
      ROS_DOMAIN_ID="$ros_domain_id" \
      GZ_PARTITION="${episode_id}_gz" \
      IGN_PARTITION="${episode_id}_gz" \
      SCENARIO="$runtime_scenario" \
      "${policy_args[@]}" \
      scripts/arena/run_baseline_episode.sh
  )
done < "$plan_path"

((checked > 0)) || fail 'no plan rows matched the requested filters'
printf 'PREFLIGHT PASS: selected=%s dry_run=%s methods=%s start_at=%s limit=%s\n' \
  "$selected" "$dry_run" "$methods" "$start_at" "$limit"
