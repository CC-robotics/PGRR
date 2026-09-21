#!/usr/bin/env bash
set -euo pipefail

runtime_root=/home/preface/PGRR-online
source_scenario='/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/families_7_8_smoke/generated/arena/map_empty/bottleneck_cross_flow_merge_medium_train_r00_s91610.json'
scenario_name=bottleneck_cross_flow_merge_medium_train_r00_s91610.json
scenario_dir=outputs/student/families_7_8_smoke
episode_id=student_v78_bottleneck_cross_flow_merge_medium_train_r00_s91610_base_retry01

cd "$runtime_root"

if ! command -v docker >/dev/null 2>&1; then
  echo 'ERROR: docker CLI is unavailable in Ubuntu-22.04; restore Docker Desktop WSL integration first.' >&2
  exit 20
fi
if ! docker version >/dev/null 2>&1; then
  echo 'ERROR: Docker server is unavailable; wait for Docker Desktop Engine and retry.' >&2
  exit 21
fi
if [[ ! -f "$source_scenario" ]]; then
  echo "ERROR: source scenario is missing: $source_scenario" >&2
  exit 22
fi

mkdir -p "$scenario_dir"
destination_scenario="$scenario_dir/$scenario_name"
if [[ ! -f "$destination_scenario" ]]; then
  cp "$source_scenario" "$destination_scenario"
fi

protected_outputs=(
  "data/raw/$episode_id.jsonl"
  "data/raw/$episode_id.metadata.json"
  "data/raw/$episode_id.outcome.json"
  "outputs/logs/baseline/${episode_id}_runtime.log"
  "outputs/logs/baseline/${episode_id}_status.log"
)
for output_path in "${protected_outputs[@]}"; do
  if [[ -e "$output_path" ]]; then
    echo "ERROR: refusing to overwrite existing retry output: $output_path" >&2
    exit 23
  fi
done

RAMP_EPISODE_ID="$episode_id" \
RAMP_EPISODE_TIMEOUT_S=90 \
SCENARIO="$destination_scenario" \
scripts/arena/run_baseline_episode.sh

outcome_path="data/raw/$episode_id.outcome.json"
if [[ -f "$outcome_path" ]]; then
  printf '\nSaved outcome: %s\n' "$outcome_path"
  sed -n '1,120p' "$outcome_path"
fi
