# Related-work verification notes

Checked on 2026-08-04 against the publisher/official proceedings page and the
paper PDF or original preprint. These notes are evidence for drafting; they are
not text to copy verbatim into the manuscript.

## Platform scope and citation policy

- **Actual runtime used in this project:** the pinned Arena **ROS2 Humble Gazebo
  fallback** described in the repository's runtime manifest and manuscript. It
  is not Arena 5.0.
- **Arena 5.0 is background only.** It documents the later photorealistic ROS2
  platform direction. Its citation must not be used to imply that the reported
  experiments ran in Arena 5.0.
- Arena 5.0's RSS landing-page/Crossref author metadata differs from the
  published PDF title page. `references.bib` follows the 16-author PDF order;
  the DOI, title, venue, and year agree.
- Arena-Rosnav 2.0, Arena 4.0, Arena-Bench, All-in-One, waypoint generators,
  DR-MPC, and GP recovery are cited using their formal IEEE/RSS records rather
  than their earlier arXiv records. Existing keys are retained where
  `main.tex` already uses them.
- There is no separate peer-reviewed DWB paper. For prose about the controller,
  cite the DWA paper and the Nav2 system paper, then identify the exact DWB
  software/configuration using the
  [official Nav2 documentation](https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html).
- `wang2025fare` and `wang2026failureaware` remain original arXiv records: no
  formal proceedings or journal records were verified at this snapshot.

## Paper-by-paper reading notes

### Arena-Bench (`kastner2022arenabench`)

- **Abstract/scope:** proposes a reproducible suite for comparing obstacle
  avoidance methods in highly dynamic environments.
- **Method:** standardizes scenarios, dynamic obstacles, navigation interfaces,
  logging, and safety/efficiency metrics so classical and learned approaches can
  be run under matched conditions.
- **Experiments:** benchmarks multiple navigation approaches across dynamic
  scenarios and crowd settings, illustrating performance variation by method
  and environment difficulty.
- **Limitation/relevance:** it is a simulation benchmark rather than a
  failure-triggered recovery method. It supports our evaluation protocol, not a
  novelty claim about recovery.
- **Primary record:** <https://doi.org/10.1109/LRA.2022.3190086>

### Arena-Rosnav 2.0 (`kastner2023arena2`)

- **Abstract/scope:** restructures Arena-Rosnav into modular APIs for adding
  planners, simulators, and evaluation components, with improved pedestrian
  behavior and documentation.
- **Method:** independently deployable platform modules and unified interfaces
  connect simulation, DRL training, planners, task generation, and evaluation.
- **Experiments:** a user study evaluates usability; integrations of two new
  simulators and several planners demonstrate extensibility and comparative
  benchmarking.
- **Limitation/relevance:** it validates platform lineage and reproducibility,
  not the proposed recovery algorithm; its software generation is not identical
  to the pinned Humble fallback used here.
- **Primary record:** <https://doi.org/10.1109/IROS55552.2023.10342152>

### Arena 3.0 (`kastner2024arena3`)

- **Abstract/scope:** extends the platform toward collaborative, highly dynamic
  social-navigation settings and richer interaction tasks.
- **Method:** integrates task modes, human behavior models, simulator adapters,
  and standardized development/evaluation interfaces.
- **Experiments:** demonstration scenarios exercise the platform's social and
  multi-agent capabilities rather than testing one recovery algorithm.
- **Limitation/relevance:** an RSS demonstration/platform contribution; it is
  useful experimental context but cannot substantiate our method's efficacy.
- **Primary record:** <https://www.roboticsproceedings.org/rss20/p074.html>

### Arena 4.0 (`shcherbyna2024arena4`)

- **Abstract/scope:** reports the full ROS2 migration, a 3D asset database, and
  generative-model-based creation of human-centric worlds and scenarios.
- **Method:** combines language/diffusion-assisted world generation with
  semantically annotated assets and ROS2 benchmarking infrastructure.
- **Experiments:** evaluates platform usability and generated-world workflows,
  including a user study and benchmarking demonstrations.
- **Limitation/relevance:** it is a platform paper, and the final ICRA 2025
  system is newer than the actual Humble fallback profile used in this project.
- **Primary record:** <https://doi.org/10.1109/ICRA55743.2025.11127635>

### Arena 5.0 (`shcherbyna2025arena5`)

- **Abstract/scope:** presents a photorealistic ROS2 simulation framework for
  developing and benchmarking social navigation.
- **Method:** couples photorealistic simulation, robot/sensor integration,
  configurable social scenarios, and evaluation workflows.
- **Experiments:** the demonstration paper showcases representative platform
  workflows and navigation/benchmarking capabilities.
- **Limitation/relevance:** it is later platform background only. None of this
  project's reported runs may be labelled Arena 5.0 without a new, separately
  locked Arena 5.0 evaluation.
- **Primary record:** <https://www.roboticsproceedings.org/rss21/p092.html>

### All-in-One (`kastner2021allinone`, compatibility key)

- **Abstract/scope:** learns which established local navigation planner should
  control the robot as conditions change.
- **Method:** a DRL selector switches among a portfolio of classical/planning
  controllers using navigation observations and planner behavior.
- **Experiments:** compares the learned switch with individual planners in
  Arena dynamic-navigation scenarios and reports the benefit of adapting the
  controller choice to the situation.
- **Limitation/relevance:** learning has continuous planner-selection authority;
  it is not a bounded failure-only recovery policy and does not output temporary
  recovery subgoals. This is one of the closest hybrid-navigation comparisons.
- **Primary record:** <https://doi.org/10.1109/ICRA46639.2022.9811797>

### DRL obstacle avoidance with waypoint generators (`kastner2021waypoints`)

- **Abstract/scope:** connects a DRL obstacle-avoidance controller to a
  conventional global planner without asking the learned controller to solve
  long-range planning by itself.
- **Method:** inserts an intermediate-planner layer whose waypoint generators
  translate the global plan into local guidance for the learned avoidance
  controller.
- **Experiments:** compares the integrated systems with traditional navigation
  systems in dynamic environments and reports safety, efficiency, and path
  smoothness outcomes.
- **Limitation/relevance:** this is the closest waypoint-interface prior art,
  but its waypoint layer guides a learned local controller during nominal
  navigation. PGRR instead lets DWB execute both nominal and temporary goals
  and invokes learning only to choose a bounded recovery option.
- **Primary record:** <https://doi.org/10.1109/IROS51168.2021.9636039>

### Dynamic Window Approach (`fox1997dwa`)

- **Abstract/scope:** introduces real-time local collision avoidance under the
  velocity and acceleration constraints of a mobile robot.
- **Method:** searches dynamically reachable translational/angular velocities,
  simulates short trajectories, and scores heading, clearance, and speed.
- **Experiments:** demonstrates real-time obstacle avoidance on mobile robots
  and in representative navigation situations.
- **Limitation/relevance:** a short-horizon local optimizer can enter local
  minima, freeze, or oscillate in reciprocal social interactions. DWB is Nav2's
  extensible implementation family, not a separate paper contribution.
- **Primary record:** <https://doi.org/10.1109/100.580977>

### Reciprocal n-body collision avoidance / ORCA (`vandenberg2011orca`)

- **Abstract/scope:** formulates collision-free reciprocal motion for multiple
  independently moving agents.
- **Method:** converts pairwise velocity-obstacle constraints into half-planes,
  assigns each agent half the avoidance responsibility, and solves a small
  linear program for the closest admissible velocity.
- **Experiments:** demonstrates efficient multi-agent simulations and robotic
  navigation examples with dense reciprocal motion.
- **Limitation/relevance:** assumes reciprocal agents, observable motion, and a
  compatible velocity choice; real pedestrians need not satisfy those
  assumptions. It is background for social interaction, not learned recovery.
- **Primary record:** <https://doi.org/10.1007/978-3-642-19457-3_1>

### Nav2 / The Marathon 2 (`macenski2020marathon2`)

- **Abstract/scope:** describes the ROS2 Navigation2 system and a long-duration
  autonomous navigation demonstration.
- **Method:** uses modular planner/controller plugins, behavior-tree task
  orchestration, lifecycle management, costmaps, and recovery behaviors.
- **Experiments:** exercises the integrated navigation stack over an extended
  autonomous run, testing practical system reliability rather than only a local
  planner in isolation.
- **Limitation/relevance:** it is a navigation-system paper and does not isolate
  DWB or study learned, failure-triggered social recovery. It supports the
  implementation provenance of our classical stack.
- **Primary record:** <https://doi.org/10.1109/IROS45743.2020.9341207>

### Socially attentive RL / SARL (`chen2019sarl`)

- **Abstract/scope:** addresses crowd navigation with an attention-based deep
  reinforcement learning policy that reasons over multiple people.
- **Method:** encodes robot--human interactions and learns attention weights so
  the policy can focus on the most relevant agents when choosing motion.
- **Experiments:** compares against prior crowd-navigation policies in simulated
  multi-human settings using success, collision, and navigation-efficiency
  measures, with a robot demonstration supporting feasibility.
- **Limitation/relevance:** the learned policy controls routine navigation
  continuously and commonly relies on structured human states; our deployed
  recovery policy is observation-limited and activated only around failure.
- **Primary record:** <https://doi.org/10.1109/ICRA.2019.8794134>

### Social navigation survey (`mavrogiannis2023survey`)

- **Abstract/scope:** synthesizes the core challenges, models, evaluation
  practices, and open questions in social robot navigation.
- **Method:** organizes prior work around interaction modeling, prediction,
  planning/learning, social compliance, datasets, and evaluation.
- **Experiments:** no new navigation policy experiment; evidence is a structured
  review of the literature and its evaluation conventions.
- **Limitation/relevance:** it supplies terminology and guards against broad
  novelty claims, but cannot serve as empirical evidence for this system.
- **Primary record:** <https://doi.org/10.1145/3583741>

### Local recovery from human demonstrations (`delduchetto2018recovery`)

- **Abstract/scope:** explicitly targets repeated local-navigation failures by
  learning recovery behavior from human demonstrations.
- **Method:** couples failure recognition with locally learned recovery policies
  and expands demonstrations when existing behavior remains insufficient.
- **Experiments:** evaluates learned recoveries on a mobile robot in navigation
  failure cases and compares behavior before and after demonstration-based
  recovery learning.
- **Limitation/relevance:** demonstrations require human effort and the learned
  action is local control rather than our finite, planning-masked temporary-goal
  interface. It is the most direct recovery-learning prior art and must be
  discussed prominently.
- **Primary record:** <https://doi.org/10.1109/LRA.2018.2861080>

### GP-based robust planning and recovery (`mohammad2024gprecovery`)

- **Abstract/scope:** proactively estimates navigation/planning reliability in
  unknown environments and invokes recovery before repeated failure.
- **Method:** uses a Gaussian-process model of planning behavior/risk together
  with a search for a state from which robust planning can resume.
- **Experiments:** evaluates agile navigation and recovery in simulated and
  physical unknown/cluttered environments against planning baselines.
- **Limitation/relevance:** the main problem is unknown-environment robust motion
  planning rather than reciprocal social navigation, imitation, or DAgger; its
  predictive recovery-state search is nevertheless close conceptual prior art.
- **Primary record:** <https://doi.org/10.1109/ICRA57147.2024.10610382>

### DAgger (`ross2011dagger`)

- **Abstract/scope:** reduces sequential imitation learning to no-regret online
  learning to address the distribution shift of one-shot behavior cloning.
- **Method:** repeatedly rolls out the current learner, queries the expert on
  learner-visited states, aggregates those labels, and retrains on the growing
  dataset.
- **Experiments:** sequential prediction/control examples show greater robustness
  than training only on expert-state demonstrations.
- **Limitation/relevance:** it assumes continued access to a sufficiently good
  expert and can be expensive or unsafe when querying on-policy states. Our
  simulator planning expert makes those queries feasible; two rounds are an
  engineering choice, not a new DAgger theorem.
- **Primary record:** <https://proceedings.mlr.press/v15/ross11a.html>

### Invalid-action masking (`huang2022invalidmasking`)

- **Abstract/scope:** analyzes why masking invalid actions works in policy
  gradient algorithms and how it compares with negative rewards for illegal
  choices.
- **Method:** masks invalid logits before sampling/normalization and derives the
  resulting policy-gradient update; alternative masking practices are compared.
- **Experiments:** controlled environments with increasingly large invalid
  action spaces show the training and sample-efficiency consequences of masking.
- **Limitation/relevance:** validity must be supplied correctly by the
  environment. The paper supports the mechanics of action masking, not the
  correctness or safety completeness of our geometric mask.
- **Primary record:** <https://doi.org/10.32473/flairs.v35i.130584>

### DR-MPC (`han2024drmpc`, compatibility key)

- **Abstract/scope:** combines learned social interaction behavior with the
  structure and constraints of model-predictive control for real-world social
  navigation.
- **Method:** a deep residual component augments an MPC backbone instead of
  replacing the whole controller, retaining model-based optimization while
  learning interaction corrections.
- **Experiments:** reports simulation and real-world social-navigation tests and
  comparisons with classical and learned alternatives.
- **Limitation/relevance:** learning affects nominal control continuously and is
  tied to an MPC formulation; our intervention is failure-triggered and chooses
  discrete recovery options subsequently executed by Nav2.
- **Primary record:** <https://doi.org/10.1109/LRA.2025.3546106>

### Failure-aware learning from demonstration (`wang2026failureaware`)

- **Abstract/scope:** uses both successful and failed experience to improve safe
  robot navigation from demonstrations.
- **Method:** separates policy learning from successful demonstrations while
  using failure information to shape value/risk estimation and discourage
  unsafe behavior.
- **Experiments:** the preprint reports navigation evaluations in simulation and
  a real-world setting against imitation/offline-learning alternatives.
- **Limitation/relevance:** this is a 2026 preprint without a verified formal
  venue at the check date. It learns failure-aware navigation rather than
  planning-expert recovery actions on learner-induced failure states.
- **Primary record:** <https://arxiv.org/abs/2604.23360>

### Failure resilience in learned visual navigation (`wang2025fare`)

- **Abstract/scope:** augments visual imitation-learning policies so that they
  can detect, recognize, and recover from out-of-distribution failures.
- **Method:** shapes the policy representation for OOD detection and
  recognition without explicit failure data, then uses the recognized failure
  evidence to inform heuristic recovery.
- **Experiments:** the preprint reports real-world recovery across two visual
  navigation policy architectures and a long indoor/outdoor route.
- **Limitation/relevance:** Fare starts from an end-to-end visual policy and
  treats policy OOD as the failure signal. PGRR retains a classical nominal
  controller, detects navigation interaction failures from LiDAR and progress
  histories, and learns among planning-masked recovery options.
- **Primary record:** <https://arxiv.org/abs/2510.24680>

## Method comparison matrix

`Yes (train)` means privileged information is confined to training/labeling.
The row for this work describes the currently evidenced imitation-learning
version; PPO and a learned detector are not credited as completed contributions.

| Method | Classical planner normally active | Failure-only intervention | Recovery demonstrations/expert | Privileged training information | DAgger | RL refinement | Temporary-subgoal output | Dynamic social evaluation |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| DWA/DWB | yes | no | none | no | no | no | no, velocity command | not intrinsically social |
| ORCA | no classical global stack assumed | no | analytic reciprocal model | no | no | no | no, reciprocal velocity | yes, reciprocal agents |
| SARL | no, learned policy is normally active | no | RL reward/simulator | structured human state during learning/testing | no | yes | no, navigation action | yes |
| All-in-One | planner portfolio under learned switch | no | planner performance through RL | simulator training | no | yes | no, planner selection | yes |
| Waypoint generators | conventional global planner; learned local avoidance | no | none | simulator training of the DRL controller | no | yes | intermediate guidance for learned control, not a recovery subgoal | highly dynamic obstacles |
| Del Duchetto et al. | yes | yes | human recovery demonstrations | no simulator privilege required | incremental LfD, not canonical DAgger | no | local recovery control | failure cases, limited social focus |
| GP robust recovery | yes | yes/proactive | GP risk model and recovery-state search | learned/modelled planning outcomes | no | no | recovery state | unknown/cluttered, not social focus |
| DR-MPC | MPC backbone | no dedicated failure boundary | learned residual | training trajectories | no | learned residual policy | no, continuous MPC correction | yes |
| Fare | no, visual IL policy is normally active | OOD-triggered | heuristic recovery informed by OOD recognition | no explicit failure data | no | no recovery RL | no, corrective learned-policy/recovery control | real-world visual navigation, not a social benchmark |
| This work, current IL version | yes, Nav2 DWB | yes | privileged short-horizon rollout expert | yes (train only) | two rounds | **not completed/claimed** | yes, 21 subgoals + 4 modes | preliminary Humble/Gazebo fallback pilot |

## Safe positioning for an EI-length manuscript

- **Primary direct comparisons:** All-in-One for hybrid classical/learning
  control; waypoint generators for connecting learned avoidance to a global
  plan; Del Duchetto et al. for learned navigation recovery; GP recovery for
  proactive failure/recovery-state reasoning; Fare for learned-policy failure
  recognition and recovery; DR-MPC for residual hybrid social navigation.
- **Methodological foundations:** DWA/Nav2, DAgger, and invalid-action masking.
- **Platform/evaluation provenance:** Arena-Bench and Arena-Rosnav 2.0; Arena
  3.0--5.0 should be compressed into platform evolution, with Arena 5.0 clearly
  labelled background only.
- **Secondary background if space permits:** ORCA, SARL, and the social-navigation
  survey.
- Defensible distinction: the classical planner remains in charge nominally; an
  observable failure trigger invokes an interpretable, finite recovery option;
  privileged rollout planning generates labels; DAgger covers learner-induced
  states; and one planning-derived mask is shared by training and deployment.
- Do not claim first navigation recovery, first failure prediction, first
  planning/IL/RL combination, collision-free guarantees, or general social
  navigation superiority.
- Do not claim PPO or learned-detector gains until closed-loop, locked validation
  actually supports them. Current evidence supports a preliminary feasibility
  and safety--time trade-off statement, not statistical superiority.
