#!/usr/bin/env bash
# Two isolated train prototypes; refuse to overwrite prior runs.
set -eu
cd /home/preface/PGRR-online
source_root='/mnt/c/Users/28646/Documents/ChatGPT/New project/PGRR/outputs/student/families_7_8_smoke'
dest=outputs/student/families_7_8_smoke
mkdir -p "$dest"
for scenario in bottleneck_cross_flow_merge_medium_train_r00_s91610 goal_approach_lateral_interruption_low_train_r00_s91700; do
  episode="student_v78_${scenario}_base"
  if test -e "data/raw/${episode}.jsonl"; then
    echo "Refusing existing episode: $episode"
    continue
  fi
  cp -n "$source_root/generated/arena/map_empty/$scenario.json" "$dest/$scenario.json"
  set +e
  RAMP_EPISODE_ID="$episode" RAMP_EPISODE_TIMEOUT_S=90 SCENARIO="$dest/$scenario.json" \
    scripts/arena/run_baseline_episode.sh > "$dest/${episode}_console.log" 2>&1
  result=$?
  set -e
  echo "$episode runner_exit=$result"
  tail -5 "$dest/${episode}_console.log"
  if test -f "data/raw/${episode}.outcome.json"; then
    cat "data/raw/${episode}.outcome.json"
  fi
done
