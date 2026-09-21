# PGRR 学生作业材料索引

更新日期：2026-09-09  
用途：给教授快速查看“已经做了什么、证据在哪里、下一步需要确认什么”。

> 说明：本目录中的内容是学习、复现诊断和后续实验设计材料。它们**不是**
> `outputs/moderate/final/` 中的公开最终证据，也没有更改冻结的
> `moderate_v6` 测试集、最终 checkpoint 或算法阈值。

## A. 作业一：环境、复现与原理学习

| 材料 | 内容与可展示结论 |
|---|---|
| `01_environment_and_reproduction.md` | Windows 离线环境和 WSL2/ROS2/Arena 在线环境的搭建记录；已完成 build 与 smoke。 |
| `02_dwb_and_imitation_learning_notes.md` | 面向初学者的 DWB、专家标签、BC、DAgger 与部署掩码笔记。 |
| `09_dagger_readonly_diagnostic_plan.md` | DAgger 训练记录的只读诊断问题与复现方式。 |
| `10_dagger_provenance_snapshot.md` | 已提交 DAgger 配置、manifest、checkpoint 和可读取指标的来源快照。 |
| `outputs/student/bc_smoke/` | 小规模 BC 学习 smoke 产物，仅用于验证学习链路；不能作为论文结果。 |
| `outputs/student/dagger_diagnostic/` | 从已提交 JSON 汇总的 DAgger 指标与训练/验证差距描述，不改变模型选择结论。 |

## B. 作业二：模块化重构准备（尚未迁移生产代码）

| 材料 | 当前结论 |
|---|---|
| `07_module_map_and_refactor_scope.md` | 恢复节点与核心/ML 模块地图，标出高耦合入口。 |
| `12_refactor_regression_matrix.md` | 重构前应复跑的测试矩阵；已记录基线单元测试通过。 |
| `15_observation_builder_extraction_boundary.md` | 观测构建可抽取的纯数据边界，以及 ONNX 输入等价性要求。 |
| `16_decision_coordinator_extraction_boundary.md` | 决策协调规则可拆边界；ROS 执行和安全敏感部分暂留节点。 |
| `17_refactor_synthetic_fixture_plan.md` | 8 个合成夹具，用于重构前后逐项对比动作掩码和最终决策。 |
| `27_teacher_direction_and_paper_workplan.md` | 根据老师逐项回复收敛的接口层边界、独立新 benchmark 与执行顺序。 |

教授需确认后才进入下一步：是否按“观测构建器 → 决策协调器”的顺序实施最小代码迁移。

## C. 作业三：算法、场景和实验表达

| 材料 | 当前结论 |
|---|---|
| `03_system_scenario_simulation_diagrams.md` | 算法框架、场景空间、在线/离线边界的 Mermaid 源稿。 |
| `13_homework_three_figure_guide.md` | 图应表达的重点、适合放入汇报/PPT的位置。 |
| `14_new_experiment_evidence_table.md` | 新实验的结果行、配对比较与日志字段清单。 |
| `08_new_scenario_parameter_draft.md` | 4 组待确认的新场景参数草案；尚未编译/执行。 |
| `11_independent_experiment_split_template.yaml` | 独立新实验的数据划分模板，明确不复用冻结 test。 |
| `11_data_split_checklist.md` | 场景与种子层面切分、保密 test 的检查表。 |
| `28_extension_paper_materials_outline.md` | 新 benchmark 的论文素材骨架、变量表、结果空模板与写作自查清单；不含任何结果。 |
| `configs/experiments/pgrr_extension_v1_train_validation.yaml` | 老师给定的两场景族、3 个密度、train/validation 的 seed 计划；test 只保留规则，不生成。 |
| `scripts/student/validate_extension_split.py` | 独立新实验的条件清单与 seed 校验器；不会调用 ROS、生成场景或启动训练。 |
| `29_extension_figure_caption_draft.md` | 扩展论文算法图的 Mermaid 图源、英文图注和中文讲解稿；仍是草稿。 |
| `scripts/student/analyze_dagger_metrics.py` | 第一个 CLI 兼容适配例：参数解析 → request → service → 原 CSV/Markdown 输出。 |
| `scripts/student/render_extension_paper_tables.py` | 从独立新实验配置自动生成场景变量表和 split/seed 表；不读取任何结果。 |
| `scripts/student/audit_extension_catalog.py` | 独立配置审计器，检查老师指定的场景变量、split、seed 与禁用测试边界。 |
| `scripts/student/compile_extension_train_validation.py` | 两个新场景族的隔离 smoke 编译器，只写入 `outputs/student` 的 train/validation JSON 与预览图。 |
| `30_extension_scenario_smoke_record.md` | 两个新场景族的 JSON、静态可达性与预览 smoke 记录；明确不含 ROS 或方法结果。 |
| `31_arena_runtime_smoke_readiness.md` | Arena/ROS smoke 的已完成准备、当前 Docker WSL Integration 阻塞及恢复后安全运行边界。 |
| `32_extension_task_setting_figure.md` | 两个新场景族的任务设置图、英文图注和使用边界；不含导航结果。 |
| `33_extension_runtime_smoke_result.md` | 已在 Arena 实际执行的单个训练场景 smoke 记录：900 条遥测、终止为 TIMEOUT；仅验证运行链路，不构成性能结论。 |
| `34_eight_family_extension_design_draft.md` | 八类独立动态交互情境的失败机制、变量、对照和 PGRR 恢复检验设计；目前只有前两类完成单例 smoke。 |
| `configs/experiments/pgrr_extension_v1_eight_family_draft.yaml` | 八类协议草案：前两类已 smoke，其余六类尚不可执行；固定 train/validation 种子规则与四方法对照。 |
| `scripts/student/audit_eight_family_draft.py` | 自动检查八类覆盖、216 个非测试条件、DAgger/train 和冻结测试集边界。 |
| `35_recurrent_crossing_geometry_smoke.md` | 第 3 类双向循环交叉行人的可编译训练 JSON、预览与静态检查记录；尚未进入 Arena。 |
| `36_head_on_deadlock_geometry_smoke.md` | 第 4 类狭窄走廊对向相遇的训练 JSON、静态可达性和预览记录；等待 Arena smoke。 |
| `37_closing_gap_geometry_smoke.md` | 第 5 类双行人关闭通行间隙的训练 JSON 与预览记录；等待 Arena smoke。 |
| `38_lead_stop_geometry_smoke.md` | 第 6 类前方行人同向移动后停住的训练 JSON 与预览记录；停止时刻待 Arena 确认。 |
| `39_bottleneck_cross_flow_design.md` | 第 7 类瓶颈横向人流汇入的参数与比较问题草案；尚未编译。 |
| `40_goal_approach_interruption_design.md` | 第 8 类接近目标时侧向中断的参数与比较问题草案；尚未编译。 |
| `41_eight_family_smoke_summary.md` | 六个已执行 Base smoke 与第 7/8 类设计状态的诚实汇总表；不含 PGRR 比较结果。 |
| `42`—`47` 系列材料 | 第 7/8 类编译与 Arena smoke、privileged actor 运动审计、PGRR 第 7 类功能 smoke 及恢复轨迹审计。 |
| `configs/experiments/pgrr_extension_v1_eight_family_pilot.yaml` | 8 个已运行训练场景的可执行开发协议，固定路径、哈希、真实运动机制和 32 次分阶段配对试运行；不含 test。 |
| `scripts/student/validate_eight_family_pilot.py` | 校验八类协议、场景/模型哈希、种子、元数据、train-only 边界和计划 episode 数。 |
| `48_eight_family_executable_pilot_protocol.md` | 用通俗语言说明八类当前真实实现、Base smoke、不能夸大的部分及下一阶段执行规则。 |
| `49_minimal_pilot_family1_pair_result.md` | 第 1 类 Base/PGRR 同场景实跑：二者均在目标附近 TIMEOUT，PGRR 未触发；如实记录为区分度不足的开发负结果。 |
| `50_minimal_pilot_family2_pair_result.md` | 第 2 类 Base COLLISION、PGRR TIMEOUT；恢复链触发并避碰但未完成，且 Base 属于静态几何碰撞，不能夸大为行人避碰。 |
| `scripts/student/run_eight_family_minimal_pilot.sh` | 16 次 Base/PGRR 配对运行器；支持 dry-run、分段执行、哈希检查和拒绝覆盖。 |
| `scripts/student/collect_eight_family_pilot_results.py` | 从 WSL 原始 episode 自动收集 outcome、哈希、重试谱系和 PGRR 恢复摘要；当前汇总为 3/8 对。 |
| `51_minimal_pilot_family3_pair_result.md` | 第 3 类两者均 TIMEOUT；PGRR 频繁恢复且目标进展明显较差，Base 原启动失败与有效 retry01 均被保留。 |
| `52_minimal_pilot_family4_pair_result.md` | 第 4 类 Base 发生动态行人碰撞，PGRR 转为恢复序列超时的 PLANNER_FAILURE；避碰但未解决任务。 |
| `53_minimal_pilot_family5_pair_result.md` | 第 5 类 Base 动态行人碰撞、PGRR 超时；恢复原目标 5 次但只使用 WAIT/BACKUP/CONTINUE，仍未脱困。 |
| `54_minimal_pilot_family6_pair_result.md` | 第 6 类 Base 与前导行人碰撞、PGRR 在相近位置超时；虽尝试 1 次临时子目标，仍未越过阻塞。 |
| `55_minimal_pilot_family7_pair_result.md` | 第 7 类 Base 在瓶颈与行人碰撞、PGRR 尝试两个临时子目标后仍超时。 |
| `56_minimal_pilot_family8_pair_result.md` | 第 8 类 Base 在目标附近与行人碰撞、PGRR 保守避让后超时且未恢复原目标。 |
| `57_eight_family_minimal_pilot_complete.md` | 完整 8 类诊断：Base 6 碰撞/2 超时，PGRR 7 超时/1 规划失败，双方 0 到达；比较器阶段暂停。 |
| `58_eight_family_recovery_progress_diagnostic.md` | 逐帧检查八个 PGRR 回合：30 次恢复中仅 5 次取得原始目标正进展，恢复状态占总时间 39.2%。 |
| `59_recovery_cycle_failure_classification.md` | 将 30 个循环的触发、动作与进展对齐：含学习决策的循环 22/25 无正进展，学习动作 90% 为 WAIT/BACKUP。 |
| `60_recovery_progress_interface_prototype.md` | 实现未接入运行时的纯 Python 循环评价接口，区分目标未恢复、危险未解除、进展不足和快速再触发。 |
| `61_existing_trace_recovery_contract_probe.md` | 将 30 个真实恢复循环接入离线评价：30/30 原目标已恢复、28/30 危险已清除，但 0/30 达到 0.25 m 任务进展。 |
| `62_mask_policy_emergency_attribution.md` | 拆分掩码、策略和紧急控制：50/58 次可解析学习决策只允许 WAIT/BACKUP，确定掩码链为首要调查对象。 |
| `63_upstream_mask_chain_audit.md` | 逐层还原掩码：50 次仅 WAIT/BACKUP 中有 46 次在第一条已记录约束前就已收缩，调查重点转向上游候选集与安全筛选。 |
| `64_runtime_mask_pipeline_static_audit.md` | 解析真实运行时调用链，将上游临时子目标消失进一步定位到地图、LiDAR 和路径走廊三层，并记录遥测盲区。 |
| `65_upstream_mask_layer_replay.md` | 用四个确定性合成输入实际回放地图、LiDAR、路径走廊三层，验证每层的独立删除行为与结论边界。 |
| `66_real_log_replay_field_audit.md` | 审计 60 个真实学习决策的回放字段：位姿、180 维 LiDAR、全局路径齐全，可近似回放；地图和原始扫描几何缺失，不能精确回放。 |
| `67_approximate_real_mask_replay.md` | 近似回放 58 个真实决策：29 次集合完全一致；46 次零候选中 27 次可由记录的扫描/路径近似复现，明确保留非因果边界。 |
| `68_train_only_mask_telemetry_contract.md` | 实现尚未接入 ROS 的逐层掩码记录契约：默认关闭、连续性检查、禁止未声明重新放行，并规定未来 train-only 等价性门槛。 |
| `69_mask_trace_equivalence_gate.md` | 四种合成输入验证记录器开/关时三层 mask 与最终动作一致，为默认关闭的最小 ROS 接入建立前置门槛。 |
| `70_minimal_ros_mask_trace_integration.md` | 将三层记录器以默认关闭参数接入真实恢复管理器；222 项扩大回归通过，并保留尚未运行 Arena 的结论边界。 |
| `71_mask_trace_smoke_preflight.md` | 实际生成 train-only smoke 安全预检；场景与启动契约就绪，同时记录 Docker/WSL 当前不可用的真实运行阻塞。 |
| `72_live_mask_trace_smoke_result.md` | Docker 恢复后完成真实 train-only PGRR smoke：896 个样本、110 个三层完整轨迹；结果为 TIMEOUT，只验证诊断链路。 |
| `73_live_mask_layer_attribution.md` | 对 110 次真实决策逐层统计：85 次在 LiDAR 层首次清空临时子目标，25 次在路径走廊层首次清空，地图层为 0。 |
| `74_mask_trace_replication_result.md` | 五个非冻结回合复核：两个 train 场景共 159 次完整轨迹重复支持 LiDAR 主导；两个 validation 场景未触发，跨 split 结论尚未建立。 |
| `75_validation_trigger_coverage_audit.md` | 区分 validation 的真正无信号与 emergency-only：对角场景分数全零，head-on validation 实际进入紧急停车但未进入子目标选择。 |
| `76_validation_selector_candidate_preflight.md` | 生成并静态预检一个 lead-stop validation 候选；依据同族 train 的 selector-positive 结果选择，未运行正式实验。 |
| `77_recovery_manager_structural_baseline.md` | 作业二的可复现结构基线：量化 1873 行/52 方法节点和两个候选拆分边界，未迁移生产代码。 |
| `78_extension_evidence_claim_ledger.md` | 作业三/论文证据台账：由 checked-in CSV/JSON 生成可写表述、禁止推论和来源绑定。 |
| `79_recovery_observation_builder_prototype.md` | 作业二纯 Python 观测构建器原型：固定旧整形规则与非特权接口，尚未接入 ROS。 |
| `80_observation_builder_equivalence_probe.md` | 32 个确定性双路用例逐字段比较旧 inline 规则与新 Builder，七个数组字段误差均为 0。 |
| `81_dagger_label_mask_distribution_audit.md` | 只读审计 DAgger 标签/mask 分布并核对哈希；iteration-5 WAIT-heavy，但 canonical 对照尚未就绪。 |
| `82_dagger_manifest_artifact_search.md` | 按 SHA-256 检索本地与全部 Git 历史；iteration-3/validation canonical HDF5 均未找到。 |
| `83_validation_selector_runtime_replication.md` | 非冻结 lead-stop validation 真实运行：TIMEOUT，但得到 191 次完整 selector trace，首次建立跨 split 诊断路径复现。 |
| `84_leadstop_validation_timeout_diagnosis.md` | 对 validation TIMEOUT 做哈希绑定诊断：四个恢复周期均无净进度，动作集中于 WAIT/BACKUP/REPLAN，但不作因果推断。 |
| `85_observation_shadow_comparator.md` | 作业二默认关闭的纯 Python shadow 比较器：关闭时不执行候选路径，开启时逐字段报告等价性，尚未接入 ROS。 |
| `86_observation_shadow_bounded_summary.md` | 为 shadow comparator 增加常量内存汇总器；32/32 等价、0 mismatch，不保存逐样本大数组。 |
| `87_observation_builder_input_ownership.md` | 修复 shadow 候选可能冻结控制器 `base_action` 输入的别名副作用，并增加不变性回归测试。 |
| `88_default_off_ros_observation_shadow.md` | 将 observation shadow 默认关闭地接入 ROS 节点，旧 observation 始终权威；38 项相关回归通过，尚未运行 Arena。 |
| `89_observation_shadow_launcher_preflight.md` | 标准启动器新增默认关闭的 shadow 开关并生成 train-only 运行预检；21 项测试与脚本语法检查通过，尚未运行 Arena。 |
| `90_observation_shadow_runtime_evidence_contract.md` | 节点销毁时输出一次有界 JSON 汇总，并新增严格 smoke 验证器；22 项相关测试通过，尚未运行 Arena。 |
| `91_observation_shadow_source_hash_gate.md` | 预检固定五个运行源码 SHA-256，并新增只读 WSL/runtime 核验器；当前权威工作区自检 5/5 匹配。 |
| `92_observation_shadow_wsl_sync.md` | 经差异审查、白名单备份同步和失败即停门禁，WSL 五个运行文件最终 5/5 匹配并通过语法检查。 |
| `93_observation_shadow_build_environment_blocker.md` | 实际触发 overlay 构建并定位到 Docker Desktop 未向 Ubuntu-22.04 提供 WSL 集成；构建与 Arena 均未开始。 |
| `94_observation_shadow_failure_containment.md` | 修复诊断候选异常可能中断权威控制路径的问题；异常现在被有界记录且 smoke 会拒绝不等价结果，23 项测试通过。 |
| `95_observation_shadow_thread_safe_accumulator.md` | 汇总器增加加锁和分离快照；8 线程 1000 次混合更新计数精确，24 项相关测试通过并保持常量内存。 |
| `96_eight_family_method_metric_matrix.md` | 从已签入 YAML/CSV 生成八类算法—场景—指标矩阵，分开主要结局、共同成功代价和机制诊断，并固定 train-only 解释边界。 |
| `97_eight_family_metric_telemetry_coverage.md` | 审计八类实验所需的 20 个指标：18 个可直接获得或派生，最小间距和死锁时长仍需预注册操作定义。 |
| `98_two_anchor_failure_diagnosis.md` | 汇总两个锚点的恢复周期、进展和最终mask：6/6危险解除但0/6有效进展，13/15学习决策只剩WAIT/BACKUP。 |
| `99_two_anchor_full_layer_mask_trace.md` | 实跑两个非冻结锚点并获得162次完整逐层trace；123次由observable_scan首次清空临时子目标，定位共同候选瓶颈。 |
| `100_observable_scan_geometry_audit.md` | 精确统计162次真实scan层删除模式，并以84.16%动作级一致率界定180束近似复放不足以支持放松安全约束。 |
| `101_exact_original_scan_predicates.md` | 新跑两个锚点并验证192/192原始scan谓词交集；122次全清空均由胶囊扫掠无可用动作直接形成。 |
| `102_capsule_failure_location_and_mask_cascade.md` | 定位胶囊失败在路径中段/终点，并确认89/89次最终无临时动作：55次由扫描清空，34次由后续方向让行清空。 |
| `103_anchor_constraint_intersection_audit.md` | 精确确认扫描残余34次均为动作2（0.6m、-30°），并被方向让行约束34/34删除，而非BC主动偏好后退。 |
| `104_anchor_scenario_semantic_audit.md` | 确认两个旧锚点只是永久阻塞/循环横穿压力原型，未完整编码突然停止释放和接近触发事件。 |
| `105_eight_family_core_readiness_triage.md` | 对8类场景统一设论文晋级门槛：8/8困难、7/8触发、0/8当前PGRR到达，分流为触发/恢复/语义三条任务线。 |
| `106_event_controlled_anchor_contract.md` | 固定两个事件可控train/validation锚点的三阶段语义、公平性、释放和无策略泄漏验收条件；暂不生成可执行场景。 |
| `107_event_state_machine_core.md` | 在独立场景命名空间实现可reset、一次触发、有限活跃并释放的纯Python事件状态机；8项测试通过，尚未接ROS。 |
| `108_event_contract_adapter_and_probe.md` | 将2个事件的train/validation参数适配到核心状态机并实跑4条离线轨迹；4/4完成一次触发与释放，策略路径隔离检查通过。 |
| `109_event_control_ros_wiring_preflight.md` | 完成事件控制默认关闭接线前检：前提7/7、实际接线0/6，固定源码哈希、最小接线顺序和接线后验收条件；19项相关测试通过。 |
| `110_default_off_ros_event_control_wiring.md` | 完成默认关闭的ROS事件控制源码接线、reset、独立遥测、outcome记录和启动器开关；38项回归及6/6接线检查通过，尚未构建或运行仿真。 |
| `111_event_controlled_lead_stop_candidate.md` | 实际生成首个train-only有限停顿后释放的领行人候选；非循环退出、配对公平性与事件映射校验通过，17项测试通过，尚待WSL构建和单对仿真。 |
| `112_event_lead_stop_runtime_gate.md` | 完成9/9 WSL安全同步、3/3 ROS包构建和首次真实配对门；Base事件触发/释放有效但超时，PGRR两次运行均无效，场景未晋级并转入控制场景诊断。 |
| `113_pgrr_runtime_control_and_lead_stop_v2.md` | 用历史train场景确认PGRR运行链健康；领行人v2得到Base碰撞/PGRR规划失败的有效配对，但碰撞归因静态几何且PGRR未到达，故不晋级并转向closing-gap。 |
| `114_event_closing_gap_open_runtime.md` | 完成开放空间双行人closing-gap同种子真实配对；两方法事件均完整触发/释放但都在终点附近超时，故保存负结果、不调种子并拒绝晋级。 |
| `115_frozen_matched_case_shortlist.md` | 只读核对完整冻结结果：26个Base未到达/PGRR到达条件覆盖5/8族；按透明规则筛出8条定性episode例子（不是8个场景），Ruff及2项测试通过。 |
| `116_eight_case_evidence_readiness.md` | 审计8条冻结episode例子的五方法结果、场景、原始轨迹和既有媒体：8/8可做辅助结果表，1/8已有验证发布图，但不计入八场景目标。 |
| `117_post_meeting_progress_and_next_research_route.md` | 面向教授重写的阶段报告，说明作业二接口层/观测Builder/shadow进度，以及场景实验已完成工作、当前障碍和后续待确认事项；明确8条episode不等于8个场景。 |
| `118_three_later_candidate_status.md` | 澄清后续三个新候选：领行人和双行人收口已实跑但未合格；目标附近一次性横穿仅完成契约，尚未生成可运行JSON。 |
| `119_eight_scenario_requirement_correction.md` | 更正研究口径：教授要求8个可复现、可重复比较的场景，不是8次单独成功；当前新增场景合格数为0/8，冻结8条记录仅作辅助例子。 |
| `120_fast_pgrr_advantage_scenario_discovery.md` | 基于冻结family-density结果与新场景失败诊断，提出可恢复窗口、8个优先机制、四级快速漏斗、固定晋级门和停止规则。 |
| `121_crossing_flow_medium_anchor_gate.md` | 首个crossing-flow/medium锚点完成真实固定配对：Base碰撞、PGRR避免碰撞但超时，按停止规则保存为负结果且不晋级。 |
| `122_crossing_flow_medium_v2_positive_screen.md` | 将同一横穿交互的任务距离修正为15米；Base仍在271样本动态碰撞，PGRR恢复、重入并于757样本到达，成为首个单seed正向候选。 |
| `123_crossing_flow_v2_train_replication.md` | 完成预声明的3个train seeds：Base 3/3动态碰撞、PGRR 3/3恢复后到达；保留一次0样本INVALID_RESET及唯一重试，场景晋级为训练内可复现候选但尚未独立validation。 |
| `124_crossing_flow_v2_independent_validation.md` | 三个未参与设计的validation seeds全部得到Base动态碰撞/PGRR恢复后到达，且无重试；第一个新场景通过独立验证，当前进度1/8。 |
| `125_goal_approach_lateral_v2_positive_screen.md` | 第一优先级第2场景完成15米、一次性中段横穿优化；Base动态碰撞、PGRR在事件释放和恢复原目标后到达，晋级train复现。 |
| `126_goal_approach_lateral_v2_train_replication.md` | 第2场景完成三组训练内复现：Base碰撞3/3、PGRR到达3/3且均恢复原目标；下一步为独立validation。 |
| `127_goal_approach_lateral_v2_independent_validation.md` | 第2场景完成独立validation：新种子下Base碰撞3/3、PGRR到达3/3且事件链与原目标恢复完整；确认计为2/8。 |
| `128_closing_gap_bounded_v3_positive_screen.md` | 第3场景完成有限双行人收口优化：v2揭示终点净空不足，v3同种子得到Base碰撞/PGRR到达，晋级训练复现。 |

## D. 与教授交流的材料

- [教授交流 PPT](../../outputs/student/PGRR_教授交流讨论提纲_简洁版.pptx)
- `05_meeting_topics_for_supervisor.md`：约课时的讨论提纲。
- `06_future_experiments_and_paper_questions.md`：新场景、论文证据、DAgger 第二轮候选表现等需讨论的问题。

建议交流顺序：先展示“环境和 smoke 已跑通”，再说明“未触碰冻结最终证据”，随后请教授确认新场景的研究问题、数据划分和最小重构优先级。

## E. 当前可继续做、不需要改变算法的工作

1. 把现有场景参数整理成独立实验的 YAML schema 校验清单；
2. 继续只读整理 BC/DAgger 的数据来源与评价字段；
3. 将 Mermaid 图稿排版为报告/论文插图草案；
4. 教授确认后，再开始第一个小型模块迁移及对应合成测试。
