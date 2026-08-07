# Evaluation metrics

All reported metrics are computed from the immutable episode manifest and raw
JSONL streams by `scripts/evaluate/collect_results.py`.  Time integrals use the
observed simulated-time intervals, not an assumed logging frequency.  An
episode has exactly one retained terminal class: `GOAL_REACHED`, `COLLISION`,
`TIMEOUT`, or `PLANNER_FAILURE`. `SIMULATOR_FAILURE` and `INVALID_RESET` are
counted and reported separately. A logical task permits the initial physical
attempt plus at most two retries, and only either of those two infrastructure
classes authorizes a retry. They are never silently converted into an
algorithm outcome; `COLLISION`, `TIMEOUT`, and `PLANNER_FAILURE` are accepted
without retry.

## Navigation outcomes

- **Success rate** is the mean indicator of `GOAL_REACHED`.
- **Collision, timeout, and planner-failure rates** are the corresponding mean
  terminal-class indicators.
- **Navigation time** is the last stream timestamp minus the first timestamp.
- **Path length** is the sum of Euclidean distances between consecutive
  evaluation-only privileged robot poses. Non-finite samples and physically
  impossible jumps are rejected and reported by the collector.
- **Shortest-path reference** is the length of the first non-empty Nav2 global
  plan recorded after episode activation.
- **SPL** for episode `i` is `S_i L_i / max(L_i, P_i)`, where `S_i` is the
  success indicator, `L_i` the shortest-path reference, and `P_i` the executed
  path length.
  SPL is missing, rather than guessed, when no valid reference plan exists.

## Safety and social clearance

- **Minimum human distance** is the minimum evaluation-only robot-centre to
  human-centre distance over an episode.
- **Personal-space violation ratio** is the simulated duration with nearest
  human distance below 1.2 m divided by episode duration.
- **Discomfort time** is the simulated duration with nearest human distance
  below 1.0 m.
- **Emergency-stop count** counts entries into state 4 (`EMERGENCY_STOP`), not
  logger samples spent in that state.

These distances describe geometric proximity to deterministic simulated
pedestrians. They are not a validated model of human comfort.

## Stability and intervention

- **Angular jerk** is the time-weighted mean absolute finite difference of the
  commanded angular velocity divided by its simulated-time interval.
- **Oscillation count** counts commanded angular-velocity sign changes after a
  0.05 rad/s deadband.
- **Recovery trigger count** counts entries from `NORMAL` into
  `PENDING_RECOVERY`, `RECOVERY`, or `EMERGENCY_STOP`.
- **Recovery duration** integrates time spent in states 1--4.
- **Intervention ratio** is recovery duration divided by episode duration.
- **Recovery success count** counts logged `REJOIN -> NORMAL` transitions.
  The state machine permits that transition only after the original task goal
  is active again, the failure score is below `tau_off`, and valid goal
  progress is observed. `SUCCEEDED` is the terminal navigation-success state
  and is deliberately not counted as a recovery success. No additional
  post-transition protection window is imposed by this metric. Recovery
  success is reported alongside, and never substituted for, the terminal
  navigation outcome.

## Paired inference

PGRR is paired separately with DWB, Standard recovery, Heuristic recovery, and
Uniform BC by the same scenario ID, density, map, and seed from
`outputs/moderate/final/episode_manifest.parquet`. Binary outcomes use the exact
McNemar test. Continuous paired differences use a two-sided Wilcoxon
signed-rank test; all-tie cases return a statistic of zero and p-value one.
Mean paired effects receive percentile bootstrap 95% confidence intervals with
10,000 resamples and a recorded seed. One global Holm correction covers the
predeclared comparator--endpoint family. Effect sizes and confidence intervals
are reported with p-values; no test-set parameter tuning is permitted.
