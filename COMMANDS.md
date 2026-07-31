# Command log

Commands are copied here when a gate is accepted. Raw command output is stored under `outputs/logs/`.

```bash
make preflight
make conda
make arena
make smoke
make test
```

Validated offline environment:

```bash
make conda
make test
env -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH \
  conda run -n ramp-offline python -c 'import torch; print(torch.cuda.is_available())'
```

Validated Arena runtime without activating Conda:

```bash
make arena
make smoke
scripts/bootstrap/arena_container.sh bash -lc \
  'ros2 pkg prefix arena_bringup; ros2 pkg prefix bondcpp; gz sim --versions'
```

The complete simulator and goal logs are written to `outputs/logs/arena_runtime.log` and `outputs/logs/arena_runtime_goal.log`; generated logs are intentionally not versioned.

Validated project architecture and ROS interfaces:

```bash
make test
make build
scripts/bootstrap/arena_container.sh bash -lc \
  'cd /workspace/ros_ws && colcon test && colcon test-result --verbose'
```

Validated deterministic scenarios and Gate 1 navigation:

```bash
make scenarios
env -u CONDA_PREFIX -u VIRTUAL_ENV scripts/arena/static_navigation.sh
env -u CONDA_PREFIX -u VIRTUAL_ENV \
  RAMP_EPISODE_ID=ramp_dynamic_single_base_dwb_gate1 \
  RAMP_EPISODE_TIMEOUT_S=60 scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/ramp_dynamic_single.json
env -u CONDA_PREFIX -u VIRTUAL_ENV \
  RAMP_EPISODE_ID=crossing_flow_low_train_s01200_base_dwb_gate1 \
  RAMP_EPISODE_TIMEOUT_S=200 scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_low_train_s01200.json
conda run -n ramp-offline python scripts/data/convert_raw_episode.py \
  --input-prefix data/raw/ramp_dynamic_single_base_dwb_gate1 \
    data/raw/crossing_flow_low_train_s01200_base_dwb_gate1 \
  --output data/interim/gate1_baseline.h5
make mine-failures SEED=0
conda run -n ramp-offline python scripts/evaluate/render_failure_examples.py
```

Validated rule detection, dense labels, and the ROS wrapper:

```bash
conda run -n ramp-offline python scripts/data/label_failures.py \
  --results outputs/pilot/baseline_failure_mining.csv \
  --output data/interim/gate1_failure_labels.h5 \
  --summary data/manifests/failure_label_summary.json
make test
make build
scripts/arena/smoke_failure_detector.sh
scripts/arena/smoke_recovery_manager.sh
scripts/arena/smoke_goal_mux.sh
```

Corrected head-on planner-abort smoke:

```bash
RAMP_ROS_DOMAIN_BASE=240 RAMP_GZ_PARTITION_BASE=340 \
conda run -n ramp-offline python scripts/evaluate/mine_failures.py \
  --manifest scenarios/manifests/failure_mining.yaml \
  --output outputs/pilot/corrected_head_on_base_smoke.csv \
  --family head_on_corridor --seed-min 0 --seed-max 0 \
  --source-policy base --episode-suffix strict2_base
```

Corrected-proxy 20-seed crossing pilot and paired statistics:

```bash
conda run -n ramp-offline python scripts/data/materialize_failure_mining.py --seed-count 20
conda run -n ramp-offline python scripts/evaluate/mine_failures.py \
  --manifest scenarios/manifests/failure_mining.yaml --family crossing_flow \
  --seed-min 10 --seed-max 19 --source-policy base --episode-suffix reactive13_base \
  --output outputs/pilot/corrected_crossing_base_10_19.csv
conda run -n ramp-offline python scripts/evaluate/mine_failures.py \
  --manifest scenarios/manifests/failure_mining.yaml --family crossing_flow \
  --seed-min 10 --seed-max 19 --source-policy heuristic \
  --episode-suffix reactive13_heuristic \
  --output outputs/pilot/corrected_crossing_heuristic_10_19.csv
conda run -n ramp-offline python scripts/evaluate/mine_failures.py \
  --manifest scenarios/manifests/failure_mining.yaml --family crossing_flow \
  --seed-min 17 --seed-max 19 --source-policy heuristic \
  --episode-suffix reactive13_heuristic \
  --output outputs/pilot/corrected_crossing_heuristic_17_19.csv
conda run -n ramp-offline python scripts/evaluate/summarize_gate2_pilot.py \
  --base outputs/pilot/corrected_crossing_base_10.csv \
  --base outputs/pilot/corrected_crossing_base_10_19.csv \
  --heuristic outputs/pilot/corrected_crossing_heuristic_10.csv \
  --heuristic outputs/pilot/corrected_crossing_heuristic_10_19.csv \
  --heuristic outputs/pilot/corrected_crossing_heuristic_17_19.csv \
  --json-output outputs/pilot/heuristic_comparison_crossing_20.json \
  --csv-output outputs/pilot/heuristic_comparison_crossing_20.csv
```

The initial 0-9 artifacts are `corrected_crossing_{base,heuristic}_10.csv`. Resume-safe execution produced later CSV shards after invalid resets; no algorithm row was synthesized while combining them.

Known-pose localization and expert validation:

```bash
RAMP_DISABLE_AUTO_RESET=1 scripts/bootstrap/arena_container.sh \
  grep -n "'amcl': 'false'" \
  /opt/arena_ws/src/arena/arena-rosnav/task_generator/task_generator/manager/robot_manager/robot_manager.py
env -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH \
  conda run -n ramp-offline python scripts/evaluate/validate_expert.py
pdfinfo outputs/figures/expert_validation_synthetic.pdf
conda run -n ramp-offline python scripts/data/label_expert.py \
  data/raw/head_on_corridor_high_mining_seed02_strict11_heuristic_dwb.jsonl \
  --stride 20 \
  --output data/interim/expert_strict11_smoke.h5 \
  --summary data/manifests/expert_strict11_smoke_summary.json
```

Online Oracle diagnostics on corrected known-pose train scenarios:

```bash
conda run -n ramp-offline python scripts/evaluate/mine_failures.py \
  --manifest scenarios/manifests/failure_mining.yaml \
  --output outputs/pilot/corrected_head_on_oracle9_seed2.csv \
  --family head_on_corridor --seed-min 2 --seed-max 2 \
  --source-policy oracle --episode-suffix oracle9
RAMP_EPISODE_ID=head_on_corridor_low_train_s01000_oracle5_smoke_dwb \
  RAMP_SOURCE_POLICY=oracle RAMP_EPISODE_TIMEOUT_S=120 \
  ROS_DOMAIN_ID=110 GZ_PARTITION=ramp_oracle_low5 IGN_PARTITION=ramp_oracle_low5 \
  scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/head_on_corridor_low_train_s01000.json
```

Results produced before `task_generator_known_pose.patch` are superseded for dynamic method claims.

Standard-recovery crossing run and strict-timestamp smoke:

```bash
conda run -n ramp-offline python scripts/evaluate/mine_failures.py \
  --manifest scenarios/manifests/failure_mining.yaml --family crossing_flow \
  --seed-min 0 --seed-max 19 --source-policy standard \
  --episode-suffix reactive13_standard \
  --output outputs/pilot/corrected_crossing_standard_20.csv
conda run -n ramp-offline python scripts/evaluate/mine_failures.py \
  --manifest scenarios/manifests/failure_mining.yaml --family crossing_flow \
  --seed-min 9 --seed-max 19 --source-policy standard \
  --episode-suffix reactive13_standard \
  --output outputs/pilot/corrected_crossing_standard_09_19.csv
env -u CONDA_PREFIX -u VIRTUAL_ENV \
  RAMP_EPISODE_ID=logger_strict_timestamp_smoke RAMP_EPISODE_TIMEOUT_S=5 \
  RAMP_SOURCE_POLICY=base ROS_DOMAIN_ID=130 \
  GZ_PARTITION=ramp_logger_strict_smoke IGN_PARTITION=ramp_logger_strict_smoke \
  scripts/arena/run_baseline_episode.sh \
  scenarios/generated/mining/crossing_flow_high_mining_seed00.json
```

## 2026-07-31 trigger-selection validation

```bash
RAMP_SOURCE_POLICY=oracle RAMP_EPISODE_TIMEOUT_S=120 \
  bash scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_medium_validation_s02210.json

PYTHONPATH=packages/ramp_core \
  conda run -n ramp-offline python scripts/evaluate/analyze_oracle_trigger.py \
  --prefix data/raw/crossing_flow_medium_train_s01210_gate3_base_retry1_dwb \
  --prefix data/raw/crossing_flow_medium_validation_s02210_gate3_base_dwb \
  --output outputs/pilot/oracle_trigger_replay.json
```

## 2026-07-31 synchronized high-density validation

```bash
RAMP_SOURCE_POLICY=base RAMP_EPISODE_TIMEOUT_S=120 \
  RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_sync3_base_dwb \
  scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

RAMP_SOURCE_POLICY=heuristic RAMP_EPISODE_TIMEOUT_S=120 \
  RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_sync3_heuristic_dwb \
  scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

RAMP_SOURCE_POLICY=oracle RAMP_EPISODE_TIMEOUT_S=120 \
  RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_sync3_oracle_retry1_dwb \
  scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_high_validation_s02220_sync3_base_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_sync3_heuristic_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_sync3_oracle_retry1_dwb \
  --output outputs/pilot/crossing_flow_high_validation_sync3_methods.csv
```
## Gate 4/5 observable BC and DAgger

```bash
make test
env -u CONDA_PREFIX -u VIRTUAL_ENV make build
make train-dagger

RAMP_SOURCE_POLICY=bc \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/iter_1/best.onnx \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_dagger1_dwb \
SCENARIO=scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json \
ROS_DOMAIN_ID=81 GZ_PARTITION=ramp_dagger1_val_cross \
scripts/arena/run_baseline_episode.sh
```
