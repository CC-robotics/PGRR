# Command log

Commands are copied here when a gate is accepted. Raw command output is stored under `outputs/logs/`.

## 2026-08-07 validation-only timeout remediation

The target probe and eight-family low-density regression used only the validation
split. The held-out test was not invoked:

```bash
conda run -n ramp-offline python scripts/evaluate/run_experiment.py \
  --split validation \
  --split-manifest scenarios/splits/moderate_v5_validation_timeout_probe.yaml \
  --methods pgrr \
  --jobs 1 \
  --timeout 240 \
  --output-dir outputs/moderate/v5_validation_timeout_fix_eceeca8

conda run -n ramp-offline python scripts/evaluate/run_experiment.py \
  --split validation \
  --split-manifest scenarios/splits/ei_pilot_low.yaml \
  --methods pgrr \
  --jobs 4 \
  --timeout 240 \
  --output-dir outputs/moderate/v5_validation_low_r0_regression_eceeca8

# Resume only the pre-logger task missing from the first pass.
conda run -n ramp-offline python scripts/evaluate/run_experiment.py \
  --split validation \
  --split-manifest scenarios/splits/ei_pilot_low.yaml \
  --methods pgrr \
  --jobs 1 \
  --timeout 240 \
  --output-dir outputs/moderate/v5_validation_low_r0_regression_eceeca8 \
  --resume
```

Both manifests were collected with the same immutable-artifact command shape (shown
for the eight-family regression):

```bash
conda run -n ramp-offline python scripts/evaluate/collect_results.py \
  --manifest outputs/moderate/v5_validation_low_r0_regression_eceeca8/episode_manifest.parquet \
  --raw-dir data/raw \
  --run-manifest outputs/moderate/v5_validation_low_r0_regression_eceeca8/run_manifest.json \
  --results outputs/moderate/v5_validation_low_r0_regression_eceeca8/results.parquet \
  --summary outputs/moderate/v5_validation_low_r0_regression_eceeca8/summary.csv \
  --statistics outputs/moderate/v5_validation_low_r0_regression_eceeca8/statistics.json \
  --reference-policy pgrr \
  --treatment-policy pgrr \
  --bootstrap-samples 10000 \
  --bootstrap-seed 20260807

make test
env -u CONDA_PREFIX -u CONDA_DEFAULT_ENV -u VIRTUAL_ENV \
  CONDA_SHLVL=0 scripts/bootstrap/build_overlay.sh
```

```bash
make preflight
make conda
make arena
make smoke
make test
```

Historical verified-pose high-density pilot (commit `6cf9535`):

```bash
env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=base RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02201_6cf9535_base_r1_dwb \
ROS_DOMAIN_ID=57 GZ_PARTITION=ramp_6cf9535_high2201_base \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02201.json

env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02201_6cf9535_bc_r1_dwb \
ROS_DOMAIN_ID=58 GZ_PARTITION=ramp_6cf9535_high2201_bc \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02201.json

# Repeat with scenario seed 2202, unique episode IDs, ROS domains, and partitions.
conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_high_validation_s02201_6cf9535_base_r1_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02201_6cf9535_bc_r1_dwb \
  --output outputs/pilot/crossing_flow_high_s02201_6cf9535_pair.csv

make figures
make tables
make paper
```

Locked EI test (64 algorithm episodes, four isolated workers):

```bash
python3 scripts/evaluate/run_experiment.py \
  --split test \
  --methods base bc \
  --high-density-methods standard heuristic \
  --jobs 4 \
  --timeout 180 \
  --checkpoint checkpoints/dagger/coverage_safety_aligned/best.onnx \
  --output-dir outputs/final
```

Add `--resume` after an interrupted run. Existing raw attempts are never overwritten.

Current terminal-evidence pilot (commit `8577ff1`) uses the same commands with
episode IDs and partitions suffixed by `8577ff1`, ROS domains 65--70, and all
three scenarios `s02201`, `s02202`, and `s02220`. Generate the accepted pair
CSVs and manuscript artifacts with:

```bash
for seed in s02201 s02202 s02220; do
  conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
    --prefix "data/raw/crossing_flow_high_validation_${seed}_8577ff1_base_r1_dwb" \
    --prefix "data/raw/crossing_flow_high_validation_${seed}_8577ff1_bc_r1_dwb" \
    --output "outputs/pilot/crossing_flow_high_${seed}_8577ff1_pair.csv"
done
make figures
make tables
make paper
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

DAgger iteration 2 (train-only policy shards):

```bash
conda run -n ramp-offline python scripts/train/train_dagger.py \
  --iteration 2 \
  --base-datasets data/processed/dagger_iter1_train.h5 \
  --dagger-shards \
    data/interim/dagger_iter2_crossing_flow_s01220_train.h5 \
    data/interim/dagger_iter2_crossing_flow_s01291_train.h5 \
    data/interim/dagger_iter2_crossing_flow_s01318_train.h5 \
  --validation-dataset data/interim/temporary_blockage_validation_expert.h5 \
  --config configs/imitation/bc_uniform_scenario.yaml
```

## Deploy-aligned safety checkpoint and repeat pilot

```bash
conda run -n ramp-offline python scripts/data/regenerate_selected_labels.py \
  data/manifests/selected_label_jobs.yaml

conda run -n ramp-offline python scripts/train/train_dagger.py \
  --iteration 3 \
  --base-datasets data/processed/dagger_iter1_safety_aligned_train.h5 \
  --dagger-shards data/interim/head_on_corridor_high_train_coverage.h5 \
  --validation-dataset data/interim/multiscenario_safety_aligned_validation.h5 \
  --config configs/imitation/bc_uniform_scenario.yaml \
  --dataset-output data/processed/dagger_coverage_safety_aligned_train.h5 \
  --checkpoint-output checkpoints/dagger/coverage_safety_aligned \
  --manifest data/manifests/dagger_coverage_safety_aligned_manifest.json

RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_coverage_safety_aligned_v1_dwb \
ROS_DOMAIN_ID=144 GZ_PARTITION=ramp_coverage_safety_v1 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

conda run -n ramp-offline python scripts/evaluate/summarize_repeated_pilot.py \
  outputs/pilot/crossing_flow_safety_aligned_repeat5.csv \
  --output outputs/pilot/crossing_flow_safety_aligned_repeat5_summary.json
```

Medium-density emergency-escape regression:

```bash
env -u CONDA_PREFIX -u VIRTUAL_ENV make build
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_medium_validation_s02210_safety_escape_bc_v2_dwb \
ROS_DOMAIN_ID=178 GZ_PARTITION=ramp_safety_escape_v2 \
IGN_PARTITION=ramp_safety_escape_v2 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_medium_validation_s02210.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_medium_validation_s02210_gate3_base_dwb \
  --prefix data/raw/crossing_flow_medium_validation_s02210_safety_density_bc_v1_dwb \
  --prefix data/raw/crossing_flow_medium_validation_s02210_safety_escape_bc_v2_dwb \
  --output outputs/pilot/crossing_flow_medium_validation_escape_regression.csv
```

High-density stalled-rejoin regression:

```bash
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_rejoin_escape_bc_v2_dwb \
ROS_DOMAIN_ID=180 GZ_PARTITION=ramp_high_rejoin_v2 \
IGN_PARTITION=ramp_high_rejoin_v2 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_high_validation_s02220_sync3_base_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_safety_escape_bc_v1_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_rejoin_escape_bc_v2_dwb \
  --output outputs/pilot/crossing_flow_high_validation_rejoin_regression.csv
```

Collision-safety release diagnostic chain:

```bash
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_latched_capsule_bc_v7_dwb \
ROS_DOMAIN_ID=185 GZ_PARTITION=ramp_high_capsule_v7 \
IGN_PARTITION=ramp_high_capsule_v7 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_high_validation_s02220_rejoin_escape_bc_v4_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_hysteresis_bc_v5_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_latched_hysteresis_bc_v6_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_latched_capsule_bc_v7_dwb \
  --output outputs/pilot/crossing_flow_high_validation_safety_iteration.csv
```

Scenario-aware static-contact regression:

```bash
make test
env -u CONDA_PREFIX -u VIRTUAL_ENV scripts/bootstrap/build_overlay.sh

env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_static_aware_bc_r2_dwb \
ROS_DOMAIN_ID=193 GZ_PARTITION=ramp_high_static_aware_r2 \
IGN_PARTITION=ramp_high_static_aware_r2 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_high_validation_s02220_persistent_turn_bc_r1_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_static_aware_bc_r2_dwb \
  --output outputs/pilot/crossing_flow_high_validation_static_collision_classifier_regression.csv
```

Proxy-synchronized open-map safety regression:

```bash
make test
env -u CONDA_PREFIX -u VIRTUAL_ENV scripts/bootstrap/build_overlay.sh

env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_self_filter_bc_r6_dwb \
ROS_DOMAIN_ID=204 GZ_PARTITION=ramp_cross_high_self_filter_r6 \
IGN_PARTITION=ramp_cross_high_self_filter_r6 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_high_validation_s02220_static_aware_bc_r2_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_improving_retreat_bc_r1_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_conservative_escape_bc_r2_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_strict_forward_bc_r4_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_proxy_sync_bc_r5_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_self_filter_bc_r6_dwb \
  --output outputs/pilot/crossing_flow_high_validation_runtime_alignment_iteration.csv
```

Kinematic pedestrian-proxy validity gate and corrected low-density pair:

```bash
make test
env -u CONDA_PREFIX -u VIRTUAL_ENV make build

env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_low_validation_s02200_kinematic_proxy_bc_r1_dwb \
ROS_DOMAIN_ID=211 GZ_PARTITION=ramp_cross_low_kinematic_r1 \
IGN_PARTITION=ramp_cross_low_kinematic_r1 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_low_validation_s02200.json

conda run -n ramp-offline python scripts/evaluate/validate_human_proxy_lidar.py \
  data/raw/crossing_flow_low_validation_s02200_kinematic_proxy_bc_r1_dwb.jsonl \
  --output data/manifests/crossing_flow_low_validation_s02200_kinematic_proxy_bc_r1_lidar_consistency.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_low_validation_s02200_kinematic_proxy_base_r1_dwb \
  --prefix data/raw/crossing_flow_low_validation_s02200_kinematic_proxy_bc_r1_dwb \
  --output outputs/pilot/crossing_flow_low_validation_kinematic_proxy_pair.csv
```

Final confirmed-pose three-density precheck (the complete commands differ only in scenario,
episode ID, and isolated ROS/Gazebo domains):

```bash
env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_high_validation_s02220_confirmed_proxy_bc_r1_dwb \
ROS_DOMAIN_ID=217 GZ_PARTITION=ramp_cross_high_confirmed_bc_r1 \
IGN_PARTITION=ramp_cross_high_confirmed_bc_r1 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_high_validation_s02220.json

conda run -n ramp-offline python scripts/evaluate/validate_human_proxy_lidar.py \
  data/raw/crossing_flow_high_validation_s02220_confirmed_proxy_bc_r1_dwb.jsonl \
  --output data/manifests/crossing_flow_high_validation_s02220_confirmed_proxy_bc_r1_lidar_consistency.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_low_validation_s02200_confirmed_proxy_base_r2_dwb \
  --prefix data/raw/crossing_flow_low_validation_s02200_confirmed_proxy_bc_r3_dwb \
  --prefix data/raw/crossing_flow_medium_validation_s02210_confirmed_proxy_base_r2_dwb \
  --prefix data/raw/crossing_flow_medium_validation_s02210_confirmed_proxy_bc_r2_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_confirmed_proxy_base_r1_dwb \
  --prefix data/raw/crossing_flow_high_validation_s02220_confirmed_proxy_bc_r1_dwb \
  --output outputs/pilot/crossing_flow_density_confirmed_proxy_pairs.csv
```

Full Gazebo actual-pose validity pair (supersedes every pre-actual-pose comparison):

```bash
env -u CONDA_PREFIX -u VIRTUAL_ENV make build

env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_ACTOR_UPDATE_HZ=2.0 RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_medium_validation_s02201_full_actual_pose_bc_r2_dwb \
ROS_DOMAIN_ID=42 GZ_PARTITION=ramp_full_actual_medium2201 \
IGN_PARTITION=ramp_full_actual_medium2201 \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_medium_validation_s02201.json

conda run -n ramp-offline python scripts/evaluate/validate_human_proxy_lidar.py \
  data/raw/crossing_flow_medium_validation_s02201_full_actual_pose_bc_r2_dwb.jsonl \
  --output data/manifests/crossing_flow_medium_validation_s02201_full_actual_pose_bc_r2_lidar_consistency.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_medium_validation_s02201_full_actual_pose_base_r1_dwb \
  --prefix data/raw/crossing_flow_medium_validation_s02201_full_actual_pose_bc_r2_dwb \
  --output outputs/pilot/crossing_flow_medium_s02201_full_actual_pose_pair.csv
```

Verified-pose pair and paper generation (supersedes the preceding diagnostic):

```bash
env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=base RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_EPISODE_ID=crossing_flow_medium_validation_s02201_2164e08_base_r1_dwb \
ROS_DOMAIN_ID=51 GZ_PARTITION=ramp_2164e08_medium2201_base \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_medium_validation_s02201.json

env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=crossing_flow_medium_validation_s02201_2164e08_bc_r1_dwb \
ROS_DOMAIN_ID=52 GZ_PARTITION=ramp_2164e08_medium2201_bc \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/crossing_flow_medium_validation_s02201.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/crossing_flow_medium_validation_s02201_2164e08_base_r1_dwb \
  --prefix data/raw/crossing_flow_medium_validation_s02201_2164e08_bc_r1_dwb \
  --output outputs/pilot/crossing_flow_medium_s02201_2164e08_pair.csv

make figures
make tables
make paper
```

Verified-pose high-density overtaking pair at commit `324fcdf`:

```bash
env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=base RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_EPISODE_ID=overtaking_high_validation_s02520_324fcdf_base_r1_dwb \
ROS_DOMAIN_ID=151 GZ_PARTITION=ramp_324fcdf_overtake_base \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/overtaking_high_validation_s02520.json

env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=overtaking_high_validation_s02520_324fcdf_bc_r1_dwb \
ROS_DOMAIN_ID=152 GZ_PARTITION=ramp_324fcdf_overtake_bc \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/overtaking_high_validation_s02520.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/overtaking_high_validation_s02520_324fcdf_base_r1_dwb \
  --prefix data/raw/overtaking_high_validation_s02520_324fcdf_bc_r1_dwb \
  --output outputs/pilot/overtaking_high_s02520_324fcdf_pair.csv
```

Held-out high-density blind-corner pair at commit `fafcddd`:

```bash
env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=base RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_EPISODE_ID=blind_corner_high_validation_s02320_fafcddd_base_r1_dwb \
ROS_DOMAIN_ID=153 GZ_PARTITION=ramp_fafcddd_blind_base \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/blind_corner_high_validation_s02320.json

env -u CONDA_PREFIX -u VIRTUAL_ENV \
RAMP_SOURCE_POLICY=bc RAMP_EPISODE_TIMEOUT_S=180 \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=blind_corner_high_validation_s02320_fafcddd_bc_r1_dwb \
ROS_DOMAIN_ID=154 GZ_PARTITION=ramp_fafcddd_blind_bc \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/blind_corner_high_validation_s02320.json

conda run -n ramp-offline python scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/blind_corner_high_validation_s02320_fafcddd_base_r1_dwb \
  --prefix data/raw/blind_corner_high_validation_s02320_fafcddd_bc_r1_dwb \
  --output outputs/pilot/blind_corner_high_s02320_fafcddd_pair.csv
```

Temporary-blockage repeat and rejected bounded-backup candidate:

```bash
RAMP_SOURCE_POLICY=bc \
RAMP_BC_MODEL_PATH=/workspace/checkpoints/dagger/coverage_safety_aligned/best.onnx \
RAMP_EPISODE_ID=temporary_blockage_high_validation_s02720_d9b5ef8_bc_r1_dwb \
ROS_DOMAIN_ID=82 GZ_PARTITION=ramp_temp_selected_bc \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/temporary_blockage_high_validation_s02720.json

RAMP_SOURCE_POLICY=base \
RAMP_EPISODE_ID=temporary_blockage_high_validation_s02720_d9b5ef8_base_r1_dwb \
ROS_DOMAIN_ID=85 GZ_PARTITION=ramp_temp_selected_base \
scripts/arena/run_baseline_episode.sh \
  scenarios/generated/arena/map_empty/temporary_blockage_high_validation_s02720.json

python3 scripts/evaluate/summarize_episode_pair.py \
  --prefix data/raw/temporary_blockage_high_validation_s02720_d9b5ef8_base_r1_dwb \
  --prefix data/raw/temporary_blockage_high_validation_s02720_d9b5ef8_bc_r1_dwb \
  --output outputs/pilot/temporary_blockage_high_s02720_d9b5ef8_pair.csv

make test
make paper
```

## 2026-08-04 locked final evaluation, resume, aggregation, and relocation

The first pass used the frozen checkpoint and four workers:

```bash
python3 scripts/evaluate/run_experiment.py \
  --split test \
  --methods base bc \
  --high-density-methods standard heuristic \
  --jobs 4 \
  --timeout 180 \
  --checkpoint checkpoints/dagger/coverage_safety_aligned/best.onnx \
  --output-dir outputs/final
```

Two workers returned from a launch without an outcome artifact. The accepted resume
used three isolated ROS domains and preserved completed attempts:

```bash
env -u PYTHONPATH -u AMENT_PREFIX_PATH -u COLCON_PREFIX_PATH \
  -u CMAKE_PREFIX_PATH -u ROS_DISTRO -u ROS_VERSION \
  -u ROS_PYTHON_VERSION \
  python3 scripts/evaluate/run_experiment.py \
    --split test \
    --methods base bc \
    --high-density-methods standard heuristic \
    --jobs 3 \
    --timeout 180 \
    --checkpoint checkpoints/dagger/coverage_safety_aligned/best.onnx \
    --output-dir outputs/final \
    --resume
```

Final aggregation uses all 24 Base/PGRR pairs, 10,000 paired bootstrap samples, and one
Holm correction family:

```bash
conda run -n ramp-offline python scripts/evaluate/collect_results.py \
  --manifest outputs/final/episode_manifest.parquet \
  --raw-dir data/raw \
  --run-manifest outputs/final/run_manifest.json \
  --results outputs/final/results.parquet \
  --summary outputs/final/summary.csv \
  --statistics outputs/final/statistics.json \
  --reference-policy base \
  --treatment-policy bc \
  --bootstrap-samples 10000 \
  --bootstrap-seed 20260804

conda run -n ramp-offline python scripts/evaluate/failure_analysis.py \
  --results outputs/final/results.parquet \
  --output outputs/final/failure_analysis.md
```

The current figures, tables, video, and PDF were generated from those final artifacts.
The all-in-one release packaging check passed and created
`outputs/final/artifact_manifest.json`; the manifest is regenerated from a clean
teacher revision before the release tag:

```bash
bash scripts/reproduce_paper.sh
```

The repository move was an atomic same-filesystem rename. Existing sibling projects
under `bonus_track` were not touched:

```bash
export PROJECT_ROOT="${PROJECT_ROOT:-${HOME}/bonus_track/PGRR}"
export LEGACY_PROJECT_ROOT="${HOME}/RAMP"
export MIGRATION_BACKUP="${PROJECT_ROOT}_migration_backup_20260804"
cd "${HOME}"
mv -- "${LEGACY_PROJECT_ROOT}" "${PROJECT_ROOT}"
cd "${PROJECT_ROOT}"
```

The old host-path caches and venv were retained outside the repository rather than
deleted. The active Docker build/install/log trees were left in place after proving
they are host-path neutral:

```bash
mkdir -p "${MIGRATION_BACKUP}/ros_ws"

mv -- ros_ws/build-host ros_ws/install-host ros_ws/log-host \
  ros_ws/build.broken-hostpaths-20260730 \
  ros_ws/install.broken-hostpaths-20260730 \
  ros_ws/log.broken-hostpaths-20260730 \
  "${MIGRATION_BACKUP}/ros_ws/"

mv -- .venv-inference \
  "${MIGRATION_BACKUP}/.venv-inference"

python3 -m venv --system-site-packages .venv-inference
.venv-inference/bin/python -m pip install \
  coloredlogs==15.0.1 flatbuffers==25.12.19 humanfriendly==10.0 \
  numpy==2.2.6 onnxruntime==1.23.2

conda run -n ramp-offline python -m pip install \
  -e packages/ramp_core -e packages/ramp_ml
conda run -n ramp-offline python -m pip freeze \
  > requirements-offline.lock.txt
```

Post-move provenance checks:

```bash
test ! -e "${LEGACY_PROJECT_ROOT}"
git rev-parse --show-toplevel

rg -l "${LEGACY_PROJECT_ROOT}|${PROJECT_ROOT}" \
  ros_ws/build ros_ws/install ros_ws/log
find ros_ws/build ros_ws/install ros_ws/log \
  -type l -lname "${LEGACY_PROJECT_ROOT}*" -print

sha256sum \
  outputs/final/episode_manifest.parquet \
  outputs/final/run_manifest.json \
  outputs/final/results.parquet \
  outputs/final/summary.csv \
  outputs/final/statistics.json \
  outputs/final/offline_policy_ablation.csv \
  paper/main.pdf
```

## 2026-08-04 — publication-style manuscript revision

The narrative, figures, and tables were regenerated without changing the locked result
files:

```bash
cd "${PROJECT_ROOT}"
make figures
make tables
make paper
make test
```

The final checks include vector-figure dimensions and typography, color/shape encoding,
table provenance and units, unresolved-reference and overfull-box scans, PDF font
embedding, and the complete offline regression suite.
