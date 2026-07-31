# Related-work verification notes

Checked on 2026-08-01 against primary paper pages or authoritative bibliographic records. Arena 5.0 is not cited here because no paper record was verified; the runtime version is documented as software provenance instead.

| Work | What was checked | Relation and limitation |
|---|---|---|
| Arena-Bench, arXiv:2206.05728 | Abstract, platform scope, benchmark claims | Supplies dynamic navigation benchmarking; does not define the present failure-triggered recovery learner. |
| Arena-Rosnav 2.0, arXiv:2302.10023 | Abstract, modular API, simulator and evaluation scope | Platform lineage and reproducibility context. |
| Arena 3.0, arXiv:2406.00837 | Abstract, task modes, human-interaction models, multi-simulator design | Establishes social-navigation platform evolution. |
| Arena 4.0, arXiv:2409.12471 | Abstract, ROS2 migration and human-centric generation | Closest verified ROS2 platform paper. |
| All-in-One, arXiv:2109.11636 | Abstract and method overview | Learns a continuous planner switch; unlike this project, it does not restrict learning to bounded failure-recovery options. |
| Del Duchetto et al., DOI 10.1109/LRA.2018.2861080 | Abstract, two-layer detector/recovery method, reported experiments | Direct prior art for learned local recovery from human demonstrations. The present distinction must be automated planning demonstrations, discrete temporary subgoals, and DAgger. |
| Mohammad et al., arXiv:2402.01617 | Abstract, proactive GP failure risk and recovery-state search | Direct prior art for proactive failure detection and recovery. It is not a social-navigation DAgger method. |
| DR-MPC, arXiv:2410.10646 | Abstract, residual MPC design and real-world evaluation | Hybrid classical/learning navigation; learning continuously modifies MPC rather than intervening only on failure with discrete subgoals. |
| DAgger, PMLR 15:627--635 | Algorithm, no-regret reduction, experiments | Justifies aggregation on learner-induced states; our two rounds are an implementation choice, not a new DAgger theorem. |
| Wang et al., arXiv:2604.23360 | Abstract, success/failure data separation, offline RL evaluation | Failure-aware safe navigation is already active prior art. It uses failures for value shaping; our expert supplies positive recovery actions on policy-visited failure states. |

## Comparison matrix

| Method | Classical planner normally active | Failure-specific recovery | Planning expert | Privileged training | DAgger | Temporary subgoal output | Dynamic social evaluation |
|---|---:|---:|---:|---:|---:|---:|---:|
| All-in-One | mixed/switchable | no | no | no | no | no | yes |
| Del Duchetto et al. | yes | yes | no, human demonstrations | no | incremental LfD, not DAgger | local recovery control | limited failure cases |
| GP robust recovery | yes | yes | GP state search | learned from simulation | no | safe recovery state | not the main focus |
| DR-MPC | MPC backbone | no dedicated trigger | MPC | training data | no | continuous residual control | yes |
| Failure-aware LfD | learned policy | failure-aware safety | no | failure labels | no | continuous navigation action | navigation simulation and real world |
| This work | yes | yes, bounded option | masked short-horizon rollout | simulator truth for expert only | two rounds | yes, 21 subgoals + 4 modes | Arena Gazebo fallback pilot |

## Prohibited novelty language

- Do not claim first navigation recovery, first failure prediction, or first planning/learning combination.
- Do not claim collision avoidance guarantees.
- Do not claim PPO or learned-detector gains until those modules have completed closed-loop evaluation.
- Frame the current contribution as a system design and empirical study unless final multi-seed evidence supports a stronger algorithmic claim.
