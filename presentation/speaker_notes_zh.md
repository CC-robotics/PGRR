# PGRR 汇报逐页讲稿

阶段：`test`。讲稿与 PPT 由同一 30 页 slide specification 生成。

## 01. PGRR：规划引导、失败触发的动态社会导航恢复与重接

核心句：PGRR: Planning-Guided Failure-Triggered Recovery and Rejoin for Dynamic Social Navigation

先明确今天汇报的范围：方法、真实运行证据和严格阶段化结果。当前阶段标签会出现在每一页。

讲述要点：

- EI 会议项目汇报
- 锁定 Test 结果
- Charles Chen

## 02. 一句话结论

核心句：学习模块不是新的底盘控制器，而是受规划约束的短时恢复决策层

用一句话把层级关系讲清楚，避免听众把 PGRR 误解为端到端速度策略。

讲述要点：

- 正常状态继续使用 Nav2 DWB
- 持续风险、冻结、振荡或死锁证据才触发恢复
- 策略选择临时子目标或 WAIT / BACKUP / REPLAN / CONTINUE
- 完成后恢复原始 PointGoal 并重新接回经典导航
- 历史 v1 64/64（非 v6）：PGRR/Base 碰撞 0/24 vs 19/24、超时 16/24 vs 0/24、到达 8/24 vs 5/24；校正成功差异不显著

## 03. 动态社会导航：局部可行不等于交互可恢复

核心句：八类场景把几何约束、相互让行与突发遮挡分开检验

先按图说明八类交互几何，再强调实验没有靠调坏 DWB 制造失败；问题来自动态主体之间的短时耦合。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。 原始算法来源：Fox、Burgard 与 Thrun，The Dynamic Window Approach to Collision Avoidance，IEEE Robotics & Automation Magazine 4(1), 1997，https://doi.org/10.1109/100.580977。

讲述要点：

- 对向会车与双向流：双方局部最优轨迹互相占据
- 门口与群体封堵：几何瓶颈要求显式退让或绕行
- 交叉流与盲角：有限视野下风险快速进入控制窗口
- 超车与临时封堵：短时最优可能演化为冻结或振荡

## 04. DWB 在 Nav2 中负责什么？

核心句：全局规划给路径，DWB 在局部代价地图上持续选择速度命令

沿箭头讲清全局路径、局部代价地图、DWB 与底盘的闭环。特别指出：PGRR输出高层恢复目标，不输出底盘速度。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。 原始算法来源：Fox、Burgard 与 Thrun，The Dynamic Window Approach to Collision Avoidance，IEEE Robotics & Automation Magazine 4(1), 1997，https://doi.org/10.1109/100.580977。

讲述要点：

- Planner Server 产生通往 PointGoal 的全局路径
- Controller Server 调用 DWB 处理局部障碍与轨迹跟踪
- DWB 输出 cmd_vel；机器人执行后再以新观测滚动重算
- PGRR 不替换这条控制链，只在失败时临时改变局部目标

## 05. Dynamic Window：只搜索当前可达的速度

核心句：Dynamic Window 是 DWA 的思想来源；DWB 通过可插拔 generator 产生候选轨迹

用图从 DWA 速度窗口讲到 DWB 候选轨迹。明确 generator 可插拔，不能据图推断冻结项目一定采用 LimitedAccelGenerator 或任何特定经典 DWA generator。原始算法来源：Fox、Burgard 与 Thrun，The Dynamic Window Approach to Collision Avoidance，IEEE Robotics & Automation Magazine 4(1), 1997，https://doi.org/10.1109/100.580977。 资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- DWA 用当前速度、加速度和制动约束构造短时可达窗口
- DWB 的 trajectory generator 是可插拔接口，具体插件由配置决定
- generator 对候选控制向前 rollout，形成多条局部轨迹
- 原始 DWA 要求足够制动距离；DWB 合法性由 generator 与 critics 决定
- 本图解释 DWA 思想，不断言冻结项目采用特定 generator

## 06. DWB 如何选出一条轨迹？

核心句：多个 critic 对候选轨迹逐项评分，加权总成本最低者成为速度命令

先解释各 critic 的职责，再读加权求和。不要把示意 critic 权重说成项目实测参数，也不要把 DWB 说成学习算法。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。 原始算法来源：Fox、Burgard 与 Thrun，The Dynamic Window Approach to Collision Avoidance，IEEE Robotics & Automation Magazine 4(1), 1997，https://doi.org/10.1109/100.580977。

讲述要点：

- 障碍相关 critic：检查碰撞与足迹净空
- 路径相关 critic：约束路径对齐与偏离距离
- 目标相关 critic：鼓励朝局部目标推进并正确收尾
- 振荡等 critic：抑制不稳定或反复切换的局部动作
- 图中是官方 DWB 机制说明，不宣称本项目新增 critic

## 07. 为什么 DWB 在社会交互中仍可能失败？

核心句：局部轨迹最优不包含对方意图，也不保证跨多个滚动窗口主动解套

对照三幅小图区分正常避障、冻结和振荡。这里讲的是局部方法的适用边界，不是声称 DWB 在所有动态环境都会失败。原始算法来源：Fox、Burgard 与 Thrun，The Dynamic Window Approach to Collision Avoidance，IEEE Robotics & Automation Magazine 4(1), 1997，https://doi.org/10.1109/100.580977。 资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- 门口会车：两侧都选择前进，安全轨迹集合逐步收缩
- 对向僵持：短窗口内后退代价高，却可能是长期可恢复动作
- 滚动重规划：相邻周期的局部最优可能左右反复切换
- 参数调优能改变偏好，但不能提供失败后的显式恢复记忆

## 08. PGRR 放在哪里：失败时接管目标，不接管速度

核心句：正常导航始终由 DWB 控制，恢复层只短时选择临时子目标或离散行为

沿总体架构从左到右讲一遍，并指出虚线特权区域只在训练出现。部署侧仍通过官方 Nav2 控制接口让 DWB 执行。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- 可观测历史 → 规则失败证据 → 滞回状态机
- 候选恢复动作 → planning mask → 选定策略
- Goal Mux 保存原始 PointGoal，再发送临时子目标
- DWB 执行临时目标；确认恢复进展后重接原目标

## 09. 何时触发：多帧失败证据，而不是一次噪声尖峰

核心句：碰撞风险、冻结、振荡和死锁使用不同证据，并由滞回与 cooldown 合并

结合 DWB 社会交互失效图说明为什么要看时间历史；触发类型与最终的到达、碰撞、超时、规划失败必须分开。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。 原始算法来源：Fox、Burgard 与 Thrun，The Dynamic Window Approach to Collision Avoidance，IEEE Robotics & Automation Magazine 4(1), 1997，https://doi.org/10.1109/100.580977。

讲述要点：

- 碰撞风险：硬防护或持续闭合趋势
- 冻结：请求运动但目标进展与位移持续不足
- 振荡：角速度多次换向且没有有效推进
- 死锁：长期阻塞，经典局部控制无法自行恢复
- episode 终局仍独立保留，不用 failure score 替代

## 10. 25 个恢复动作 + Action Mask

核心句：学习策略只在规划可行的高层动作中选择，临时目标仍由 DWB 跟踪

先读左侧动作格点，再读 rollout 排名。强调 mask 是可行性约束，不是碰撞安全证明；合法临时目标最终仍交给 DWB。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- 21 个临时子目标：3 个半径 × 7 个相对方向
- WAIT、BACKUP、REPLAN、CONTINUE 四个离散行为
- 障碍内、地图外、局部不可达或不连通子目标被屏蔽
- 后方净空不足时禁止 BACKUP
- masked invalid action rate 在部署中必须为 0

## 11. 独立安全监督器

核心句：学习决策永远不能覆盖紧急停止优先级

借 dynamic-window 图解释停止距离与可制动轨迹；再说明监督器优先级高于学习决策。原地旋转与平移净空必须分开。原始算法来源：Fox、Burgard 与 Thrun，The Dynamic Window Approach to Collision Avoidance，IEEE Robotics & Automation Magazine 4(1), 1997，https://doi.org/10.1109/100.580977。 资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- 停止距离 = 制动距离 + 延迟距离 + margin
- 窄前向区域保留即时硬防护
- 偏轴风险需要时间一致的闭合证据
- 旋转净空与平移足迹停止距离分离
- 所有 emergency intervention 单独记录

## 12. 有界恢复状态机

核心句：滞回、cooldown、动作保持、重接和最大尝试共同抑制抖动

按正常路径讲状态转换，再补充红色安全抢占和失败出口。DWB 在 NORMAL、临时目标执行和 REJOIN 中仍是底层控制器。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- NORMAL → PENDING → RECOVERY → REJOIN
- 原目标在进入恢复时保存，临时目标结束后恢复
- REJOIN 只有重新产生原目标进展后才返回 NORMAL
- EMERGENCY STOP 可从任意执行状态抢占
- 超时和连续失败进入明确终止状态

## 13. 特权短时域规划专家

核心句：用未来短窗口比较所有合法恢复动作，而不是人工逐帧标注

要明确 privileged 不等于测试作弊，因为专家只产生训练标签；rollout 使用差速运动学，但部署动作仍交给 DWB。原始算法来源：Fox、Burgard 与 Thrun，The Dynamic Window Approach to Collision Avoidance，IEEE Robotics & Automation Magazine 4(1), 1997，https://doi.org/10.1109/100.580977。 资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- 读取机器人、地图、行人位置速度和短时预测
- 对每个合法候选进行差速运动学 rollout
- 联合计算碰撞、进展、社会距离、重接、平滑与时间成本
- 输出最优动作、25 维代价、mask 和 margin
- 专家只用于训练与 Oracle 分析

## 14. Behavior Cloning：先学习专家映射

核心句：BC 在专家数据分布上拟合 25 类动作，但不会主动看见自身错误后的状态

先讲普通监督学习，再用右图说明训练分布与部署分布分叉。协变量偏移是DAgger 原论文解决的核心问题之一。DAgger 来源：Ross、Gordon 与 Bagnell，A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning，AISTATS 2011，PMLR 15:627–635，https://proceedings.mlr.press/v15/ross11a.html。

讲述要点：

- LiDAR 1D CNN + 导航状态 MLP → 25 logits
- 监督目标来自特权专家在合法动作集合中的选择
- Uniform BC 是相同观测、动作和 mask 下的直接对照
- 一次小错误会改变后续观测，产生训练时稀少的恢复状态
- 因此离线 top-1 accuracy 不能替代闭环评估

## 15. BC 的误差为什么会在闭环累积？

核心句：策略一旦偏离专家轨迹，后续输入不再服从原始示范分布

沿图中的 expert distribution、learner drift 和 compounding error 讲解。不要把它包装成项目新理论，这是 DAgger 的标准动机。DAgger 来源：Ross、Gordon 与 Bagnell，A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning，AISTATS 2011，PMLR 15:627–635，https://proceedings.mlr.press/v15/ross11a.html。

讲述要点：

- 专家数据主要覆盖理想恢复路径附近的状态
- 学习器的早期误差会把机器人带入未覆盖区域
- 未覆盖区域上预测更差，继续放大轨迹偏差
- 恢复任务尤其容易出现 WAIT、BACKUP 或左右切换循环
- 需要在学习器真正访问的状态上重新询问专家

## 16. DAgger：在学习器访问的状态上询问专家

核心句：闭环采样、专家重标、数据聚合与重新训练构成迭代分布覆盖

按圆环逐步讲 rollout、query、aggregate 和 retrain。PGRR 使用有限两轮实现，不是无限在线学习，也不在 test 上继续更新。DAgger 来源：Ross、Gordon 与 Bagnell，A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning，AISTATS 2011，PMLR 15:627–635，https://proceedings.mlr.press/v15/ross11a.html。

讲述要点：

- 以当前策略在 train split 闭环运行，收集实际访问状态
- 特权专家为这些状态给出合法恢复动作标签
- 把新样本并入聚合数据集，再训练下一候选策略
- 只用固定 validation 选择是否接受候选 checkpoint
- test 在模型和协议冻结前保持关闭

## 17. PGRR 的两轮 DAgger 与模型选择

核心句：工作流完整执行两轮，但 validation 没有提升的第二候选不会进入最终模型

沿时间轴强调执行轮数与最终选中轮次不是一回事。第二候选被拒绝和 margin负结果必须保留；PPO 不是本发布贡献。DAgger 来源：Ross、Gordon 与 Bagnell，A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning，AISTATS 2011，PMLR 15:627–635，https://proceedings.mlr.press/v15/ross11a.html。

讲述要点：

- 起点：Uniform BC checkpoint 与固定训练数据
- Round 1：闭环收集策略诱导状态，专家重标并聚合
- Round 2：流程完成，但候选在 validation 上被拒绝
- 最终导出 validation 选择的 Triggered-DAgger best.onnx
- margin weighting 未改善冻结离线消融，作为负面结果保留

## 18. 训练—部署隔离与锁定规则

核心句：专家可使用仿真特权信息；部署模型只接受机器人可观测量和 planning mask

对照图中 privileged 与 deployable 两条数据路径回答信息泄漏问题，并强调DAgger 只在 train 闭环查询专家。DAgger 来源：Ross、Gordon 与 Bagnell，A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning，AISTATS 2011，PMLR 15:627–635，https://proceedings.mlr.press/v15/ross11a.html。 资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- 训练侧：行人真值与短时未来只用于专家 rollout 标签
- 部署侧：LiDAR、目标、局部路径、速度、进展与 planner 状态
- Train / validation / test 按 scenario 与 map 分离，不按 frame
- 同一 pair 的场景、地图、seed 和行人配置跨方法一致
- checkpoint、代码与协议冻结后才打开 120 条件 test

## 19. 真实 Arena/Gazebo 运行环境

核心句：不是示意图：Jackal、动态行人、静态瓶颈与 Nav2 DWB 在同一 episode 运行

指出机器人、LiDAR 可见代理、门口几何和 Gazebo 窗口。明确它不是锁定 test回合的 camera frame，也不能与遥测重建混称截图。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。

讲述要点：

- Ubuntu 22.04 / ROS2 Humble / Arena Gazebo
- Jackal / Nav2 DWB / 平面 LiDAR / 动态代理
- 历史 moderate-v5 validation 环境演示（不是另一当前版本）
- episode ID：runtime_capture_gazebo_doorway_bottleneck_medium_20260806T054015Z_3875172；pixel SHA256：5313957c3032
- 截图仅证明真实运行环境，不替代锁定 test 的总体统计

## 20. 五方法、同条件、完整证据链

核心句：从 Base DWB 到 PGRR，五种方法共享 120 个锁定条件并保留全部终局

沿证据链从 manifest、raw、Parquet、统计 JSON 讲到图表。所有方法复用同一DWB；Uniform BC 与 PGRR 只在数据聚合上不同。资料来源：Nav2 官方 DWB Controller 文档 https://docs.nav2.org/configuration/packages/configuring-dwb-controller.html；Navigation2 官方 DWB README https://github.com/ros-navigation/navigation2/blob/humble/nav2_dwb_controller/README.md。 DAgger 来源：Ross、Gordon 与 Bagnell，A Reduction of Imitation Learning and Structured Prediction to No-Regret Online Learning，AISTATS 2011，PMLR 15:627–635，https://proceedings.mlr.press/v15/ross11a.html。

讲述要点：

- Base、Standard、Heuristic、Uniform BC、PGRR 各 120 回合
- 八个 family × 三档 density × 五次重复，共 600 logical episodes
- 终局：到达、碰撞、超时、规划失败；基础设施失败另列
- 到达/碰撞/超时做配对 McNemar，并进行全局 Holm 校正
- 共同成功效率只在双方都到达的 pair 内比较
- 规划失败仅做描述性率与差值，不补做事后显著性检验

## 21. 主结果：完整终止类别

核心句：锁定 test：终止结果按四类完整报告

先确认阶段标签，再报告所有终止类别。禁止只展示成功率或只展示碰撞率。

讲述要点：

- 配对条件：120；方法 episode：600
- DWB 到达 / 碰撞 / 超时：70.8% / 29.2% / 0.0%
- PGRR 到达 / 碰撞 / 超时：90.8% / 0.0% / 1.7%
- 规划失败（描述性、非预注册推断端点）：DWB 0.0%；PGRR 7.5%；差 +7.5 个百分点
- 基础设施排除：0，未并入算法分母

## 22. 密度分层

核心句：三档密度全部展示，不做事后子集选择

按 low、medium、high 顺序解释趋势；不要把描述性差异说成显著交互效应。

讲述要点：

- Low：DWB 72.5%；PGRR 92.5%
- Medium：DWB 72.5%；PGRR 90.0%
- High：DWB 67.5%；PGRR 90.0%
- 柱状图来自同一 approved results.parquet
- 阶段：锁定 test

## 23. 八类交互族结果

核心句：聚合结果必须回到八类交互几何检查

完整矩阵用于定位方法在哪些几何交互中受益或退化，不能只截取表现好的三类。

讲述要点：

- 每个单元显示目标到达率，覆盖全部预声明 family
- 矩阵用于识别收益集中、退化和不可恢复结构
- 场景差异为描述性分析，不自动构成显著性结论
- 阶段：锁定 test

## 24. PGRR 对 Baseline 的配对效应

核心句：四个 baseline × 三个终止端点均给出配对差、区间、校正 p 与效应量

正的目标差有利；碰撞和超时则负值有利。逐项读取区间、全局 Holm pH 与 ORH。

讲述要点：

- DWB：到达 +20.0 个百分点；碰撞 -29.2 个百分点；超时 +1.7 个百分点
- Standard：到达 +23.3 个百分点；碰撞 -32.5 个百分点；超时 +1.7 个百分点
- Heuristic：到达 +7.5 个百分点；碰撞 -0.8 个百分点；超时 -3.3 个百分点
- Uniform BC：到达 +4.2 个百分点；碰撞 -0.8 个百分点；超时 -2.5 个百分点
- 右图逐端点标注 95% CI、全局 Holm p_H 与 matched OR_H

## 25. 共同成功条件下的配对效率

核心句：只在两者都到达的同一 pair 内比较效率，并保留全部失败终局

逐项读取 PGRR-DWB 配对差、95% CI 与全局 Holm p；强调只纳入共同到达 pair，不能把失败 episode 从完成率中删除。

讲述要点：

- 共同到达 pair：83；Base 与 PGRR 必须同时 GOAL_REACHED
- 时长差 PGRR-DWB：+15.877 [+11.427, +20.834] s；Holm p=<0.001
- 路径差 PGRR-DWB：+1.886 [+1.205, +2.691] m；Holm p=<0.001
- 条件于 joint success；不能删除或替代碰撞、超时和规划失败
- 阶段：锁定 test

## 26. Matched Base--PGRR 真实运行对比

核心句：固定 matched pair 公开 Base--PGRR 空间轨迹与真实终局

先核对 pair 与 raw SHA，再读轨迹和事件线；这是遥测重建，不是相机截图。

讲述要点：

- 选择规则：eligible: PGRR trigger + configured static geometry + actor routes; order: Base failure/PGRR goal, outcome contrast, PGRR goal, density, trigger count, family, seed, pair_id
- DWB 终局：COLLISION；raw SHA 3b2969e6d15e
- PGRR 终局：GOAL_REACHED；raw SHA 7c81c150788a
- pair：blind_corner_high_test_moderate_v6_r00_s87320_seed87320；scenario：blind_corner_high_test_moderate_v6_r00_s87320
- 轨迹是 JSONL/Parquet 遥测重建，不是 camera screenshot

## 27. PGRR 恢复时序（同一 Matched Pair）

核心句：恢复触发、状态切换和目标进展来自同一 PGRR raw stream

核对同一 pair、PGRR episode 和 raw SHA 后再读触发与状态线；这是遥测重建，不是相机画面。

讲述要点：

- pair：blind_corner_high_test_moderate_v6_r00_s87320_seed87320；PGRR episode：blind_corner_high_test_moderate_v6_r00_s87320_eval_pgrr_r95ec74c511bb_a0_dwb
- PGRR 终局：GOAL_REACHED；raw SHA 7c81c150788a
- 时间线包含记录的目标距离、failure score、恢复状态与触发事件
- 时间线是 telemetry reconstruction，不是 camera screenshot
- n=1 描述性运行证据；总体结论仍来自完整 outcome 分解

## 28. 失败案例与局限

核心句：降低碰撞但增加 timeout 仍然是失败转移，必须公开

结合代表性轨迹解释根因；不要用截图代替总体失败统计。

讲述要点：

- 重点检查长期 WAIT、持续 BACKUP、左右切换和重复恢复
- 规则触发可能误报或漏报，action mask 可能过于保守
- 二维 LiDAR、已知地图、离散动作和仿真人群限制外推
- 历史 v1 64/64（非 v6）显示碰撞下降伴随 timeout 上升；到达 8/24 vs 5/24 的校正比较不显著
- PPO、学习 detector、第二 planner、Flatland、硬件和形式安全均未完成

## 29. 复现与工程交付

核心句：代码、结果、图表、论文和汇报共享同一证据链

沿图展示 manifest → raw → Parquet/JSON → figures/tables → paper/report/deck 的单向证据链，并说明任何完整性检查失败都会阻止生成“final”文档。

讲述要点：

- 锁定 episode manifest、run manifest 和 results.parquet
- 保存项目 commit、Arena commit、checkpoint 与场景 SHA256
- 图表和 TeX 表格全部自动生成
- 发布门禁：test 技术报告固定 32 页；PPTX/PDF 固定 30 页
- 发布前执行测试、字体、关系、占位符和隐私审计

## 30. 结论与 Q&A

核心句：PGRR 的核心不是替代经典规划，而是让失败恢复可学习、可约束、可解释

最后说明这是锁定 test 结果；同时保留失败类别、校正显著性、joint-success 条件和局限声明。

讲述要点：

- 经典规划器保持常态控制
- 特权规划专家降低人工恢复标注成本
- DAgger 覆盖策略诱导的困难恢复状态
- 规划 mask 与有界状态机限制学习策略作用域
- 当前汇报阶段：锁定 Test 结果
