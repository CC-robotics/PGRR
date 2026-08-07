# PGRR 汇报逐页讲稿

阶段：`pending`。讲稿与 PPT 由同一 30 页 slide specification 生成。

## 01. PGRR：规划引导、失败触发的动态社会导航恢复与重接

核心句：PGRR: Planning-Guided Failure-Triggered Recovery and Rejoin for Dynamic Social Navigation

先明确今天汇报的范围：方法、真实运行证据和严格阶段化结果。当前阶段标签会出现在每一页。

讲述要点：

- EI 会议项目汇报
- 验证执行中｜数值待锁定
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

## 03. 为什么经典规划器仍会失败？

核心句：局部可行不等于动态交互可恢复

强调这些不是把 DWB 参数调坏制造的失败，而是动态社会交互下的局部决策问题。

讲述要点：

- 对向会车：双方持续占据彼此最优局部轨迹
- 门口竞争：短时最优控制造成冻结或相互抢占
- 盲角突现：有限视野下接近速度快速变化
- 临时封堵：局部规划器反复输出无效控制或振荡

## 04. 失败不是单一碰撞标签

核心句：系统区分碰撞风险、冻结、振荡和动态死锁

这页要区分触发类型与 episode 终止类型，两者不能混为一个安全分数。

讲述要点：

- 碰撞风险：前向硬防护或持续闭合趋势
- 冻结：离目标仍远、位移不足且规划器请求运动
- 振荡：角速度多次换向但目标进展不足
- 死锁：持续阻塞且短窗口无法恢复有效进展
- 最终结局仍独立记录为到达、碰撞、超时或规划失败

## 05. 研究问题

核心句：能否提高困难动态交互的恢复能力，同时不破坏正常规划稳定性？

把研究问题落到四个可验证要求：稀疏介入、合法动作、信息隔离和配对评价。

讲述要点：

- 介入应稀疏、可解释、可取消
- 学习动作必须经过规划可行性约束
- 训练可用特权监督，测试只能用机器人可观测信息
- 效果必须在相同 episode manifest 上配对比较

## 06. 贡献与边界

核心句：贡献集中在失败触发、规划专家、恢复分布学习和受限重接

最后一条很重要：主动说明当前版本不依赖 PPO 或学习检测器来成立。

讲述要点：

- 失败前触发的经典规划器恢复层
- 特权短时域规划自动生成恢复示范
- Behavior Cloning + 两轮 DAgger 覆盖策略诱导状态
- 规划 action mask + 独立安全监督 + 有界状态机
- PPO、学习 detector、第二 planner、Flatland、硬件与形式安全均非完成声明

## 07. 总体架构

核心句：训练侧可用特权规划监督，部署侧严格闭合在 LiDAR 与 Nav2 状态上

沿着图从左到右讲一遍，并指出虚线特权区域只在训练出现。

讲述要点：

- 观测构造 → 失败检测 → 滞回状态机
- 候选动作 → action mask → 恢复策略
- Goal Mux 保存原目标并发送临时子目标
- DWB 执行动作，重接后恢复常态控制

## 08. 正式观测与触发证据

核心句：部署不使用行人真值、ID 或未来轨迹

这里主动回答公平性问题：测试输入均可由机器人传感和导航栈产生。

讲述要点：

- 最近 5 帧 × 180 beams LiDAR
- 目标极坐标与前方 8 个局部路径点
- 机器人速度与 DWB 当前输出
- 10 步目标进展和角速度历史
- 规划器状态与规则失败分数

## 09. 25 个可解释恢复动作

核心句：策略做高层选择，不直接输出底盘速度

用图说明一个恢复动作最终仍经过经典局部规划，而不是绕过它。

讲述要点：

- 21 个临时子目标：3 个半径 × 7 个相对方向
- 4 个行为：WAIT、BACKUP、REPLAN、CONTINUE
- 临时目标仍由 DWB 跟踪
- 动作 ID 固定，训练、导出和 ROS 推理一致

## 10. Action Mask：先排除不可执行动作

核心句：策略只能在物理和规划上可行的候选集合内选择

强调 mask 是可行性约束，不是碰撞安全证明。

讲述要点：

- 障碍内、地图外、局部不可达或不连通子目标被屏蔽
- 明显进入动态占据区的子目标被屏蔽
- 后方净空不足时禁止 BACKUP
- 规划接口不可用时禁止 REPLAN
- masked invalid action rate 在部署中必须为 0

## 11. 独立安全监督器

核心句：学习决策永远不能覆盖紧急停止优先级

解释为什么要区分原地旋转与平移净空：安全侧墙不应永久锁死转向。

讲述要点：

- 停止距离 = 制动距离 + 延迟距离 + margin
- 窄前向区域保留即时硬防护
- 偏轴风险需要时间一致的闭合证据
- 旋转净空与平移足迹停止距离分离
- 所有 emergency intervention 单独记录

## 12. 有界恢复状态机

核心句：滞回、cooldown、动作保持、重接和最大尝试共同抑制抖动

按正常路径讲状态转换，再补充红色安全抢占和失败出口。

讲述要点：

- NORMAL → PENDING → RECOVERY → REJOIN
- 原目标在进入恢复时保存，临时目标结束后恢复
- REJOIN 只有重新产生原目标进展后才返回 NORMAL
- EMERGENCY STOP 可从任意执行状态抢占
- 超时和连续失败进入明确终止状态

## 13. 特权短时域规划专家

核心句：用未来短窗口比较所有合法恢复动作，而不是人工逐帧标注

要明确 privileged 不等于测试作弊，因为专家输出的是训练标签。

讲述要点：

- 读取机器人、地图、行人位置速度和短时预测
- 对每个合法候选进行差速运动学 rollout
- 联合计算碰撞、进展、社会距离、重接、平滑与时间成本
- 输出最优动作、25 维代价、mask 和 margin
- 专家只用于训练与 Oracle 分析

## 14. Behavior Cloning 与两轮 DAgger

核心句：DAgger 专门补充当前策略会访问、原始示范不足的恢复状态

不要只讲 top-1 accuracy；核心是策略访问分布和真实闭环选择。

讲述要点：

- LiDAR 1D CNN + 导航状态 MLP → 25 logits
- 训练先完成 Uniform BC
- 每轮在 train split 闭环运行并由专家重新标注
- 聚合数据后只在固定 validation 上选择 checkpoint
- 未选中的第二轮候选和 margin 负面结果继续保留

## 15. 训练—部署信息隔离

核心句：强监督可以来自仿真真值，但部署接口必须保持可观测

这页回答审稿人常见问题：专家使用真值是否导致部署不可实现。

讲述要点：

- privileged humans / future outcomes 只存在数据与专家侧
- 导出模型不包含真值行人张量
- ROS 推理节点只接收标准化正式观测和 mask
- schema、checkpoint manifest 与接口测试共同检查泄漏

## 16. 真实 Arena/Gazebo 运行证据

核心句：不是概念图：Jackal、动态行人、静态瓶颈和 Nav2 在同一 episode 实际运行

指出 Jackal、LiDAR 可见行人代理和门口几何；明确这是冻结场景运行证明，不能把遥测重建或该演示图冒充锁定 test 截图。

讲述要点：

- 环境：Ubuntu 22.04 / ROS2 Humble / Arena Gazebo
- 机器人与感知：Jackal / Nav2 DWB / 平面 LiDAR
- 冻结 v5 演示：doorway_bottleneck / medium / validation
- episode ID：runtime_capture_gazebo_doorway_bottleneck_medium_20260806T054015Z_3875172；pixel SHA256：5313957c3032
- 它不是锁定 v6 统计回合的 camera frame，也不替代定量实验

## 17. 八类场景 × 三档密度

核心句：从正面对向到临时封堵，覆盖不同动态交互结构

快速扫过八个小图，不逐个展开细节；强调固定模板和 seeded physical realization。

讲述要点：

- head-on、doorway、crossing、blind corner
- group blocking、overtaking、opposite streams、temporary blockage
- 每类 low / medium / high
- 地图、起终点、行人路线和 seed 写入 manifest

## 18. Split、规模与锁定规则

核心句：validation 用于选择，test 只在代码、配置和 checkpoint 冻结后打开

明确 360 和 600 是总 method-episodes，不是每个方法的数量。

讲述要点：

- moderate-v6：Train / validation / test 使用不相交 seed 和 scenario ID
- v5 Base validation 57/72，超过 75% ceiling，故 rejected 且 test 未打开
- Validation：72 条件 × 5 方法 = 360 method-episodes
- 锁定 Test：120 条件 × 5 方法 = 600 method-episodes
- 同一 pair 的场景、地图、seed 和行人配置跨方法一致
- test 结果不能反向调参

## 19. 五种闭环对比方法

核心句：从纯经典基线到训练分布聚合，逐级增加恢复能力

强调所有方法复用同一 DWB 和同一物理条件，避免基础规划器差异干扰比较。

讲述要点：

- DWB：无 PGRR 恢复层
- Standard：导航栈标准恢复
- Heuristic：规则触发 + 手工动作
- Uniform BC：相同观测、动作和 mask 的行为克隆
- PGRR：选定 DAgger checkpoint + 有界恢复闭环

## 20. 指标与统计协议

核心句：一个方法不能靠永远 WAIT 获得虚假安全优势

这页为后面的结果解释定规则：显著性、效果量和失败类别都要一起看。

讲述要点：

- 终止：到达、碰撞、超时、规划失败
- 效率：SPL、路径长度、导航时间
- 安全：最小人距、个人空间侵入、不舒适时间、紧急停止
- 恢复：触发、重接成功、持续时间、介入比例
- 配对 McNemar / Wilcoxon + bootstrap 95% CI + 全局 Holm

## 21. 主结果：完整终止类别

核心句：只接受完整终止类别，不用安全替代完成

先确认阶段标签，再报告所有终止类别。禁止只展示成功率或只展示碰撞率。

讲述要点：

- 阶段标识：验证执行中，结果尚未锁定
- 本页计划展示：五种方法的到达、碰撞、超时与规划失败
- 未读取历史 64-episode、pilot、calibration 或运行中的验证目录
- 批准结果通过 split、pair、完整性与 SHA256 检查后自动覆盖本页

## 22. 密度分层

核心句：密度效应必须展示全部 low / medium / high 单元

按 low、medium、high 顺序解释趋势；不要把描述性差异说成显著交互效应。

讲述要点：

- 阶段标识：验证执行中，结果尚未锁定
- 本页计划展示：三档密度的目标到达率与样本数
- 未读取历史 64-episode、pilot、calibration 或运行中的验证目录
- 批准结果通过 split、pair、完整性与 SHA256 检查后自动覆盖本页

## 23. 八类交互族结果

核心句：八类场景全部公开，不能只挑有利案例

完整矩阵用于定位方法在哪些几何交互中受益或退化，不能只截取表现好的三类。

讲述要点：

- 阶段标识：验证执行中，结果尚未锁定
- 本页计划展示：八个 family × 五种方法的完整目标到达矩阵
- 未读取历史 64-episode、pilot、calibration 或运行中的验证目录
- 批准结果通过 split、pair、完整性与 SHA256 检查后自动覆盖本页

## 24. PGRR 对 Baseline 的配对效应

核心句：配对效应与显著性必须来自锁定统计 JSON

正的目标差有利；碰撞和超时则负值有利。逐项读取区间、全局 Holm pH 与 ORH。

讲述要点：

- 阶段标识：验证执行中，结果尚未锁定
- 本页计划展示：PGRR 相对四个 baseline 的配对差、区间与 Holm 校正
- 未读取历史 64-episode、pilot、calibration 或运行中的验证目录
- 批准结果通过 split、pair、完整性与 SHA256 检查后自动覆盖本页

## 25. 安全—效率视图

核心句：安全、效率与完成率必须联合解释

先讲坐标含义，再强调它不能把失败 episode 从完成率中删除。

讲述要点：

- 阶段标识：验证执行中，结果尚未锁定
- 本页计划展示：最小人距与成功 episode 导航时间
- 未读取历史 64-episode、pilot、calibration 或运行中的验证目录
- 批准结果通过 split、pair、完整性与 SHA256 检查后自动覆盖本页

## 26. Matched Base--PGRR 真实运行对比

核心句：matched 运行页等待 hash-linked raw/Parquet sidecar

先核对 pair 与 raw SHA，再读轨迹和事件线；这是遥测重建，不是相机截图。

讲述要点：

- 阶段标识：验证执行中，结果尚未锁定
- 本页计划展示：预注册 doorway/medium/r00 的 Base--PGRR 空间轨迹与事件时间线；遥测重建，不是 camera screenshot
- 未读取历史 64-episode、pilot、calibration 或运行中的验证目录
- 批准结果通过 split、pair、完整性与 SHA256 检查后自动覆盖本页

## 27. PGRR 恢复时序（同一 Matched Pair）

核心句：恢复时序素材与轨迹素材必须来自同一 test pair

核对同一 pair、PGRR episode 和 raw SHA 后再读触发与状态线；这是遥测重建，不是相机画面。

讲述要点：

- 阶段标识：验证执行中，结果尚未锁定
- 本页计划展示：固定文件名的 PGRR 目标距离、failure score、恢复状态与触发时间线；遥测重建，不是 camera screenshot
- 未读取历史 64-episode、pilot、calibration 或运行中的验证目录
- 批准结果通过 split、pair、完整性与 SHA256 检查后自动覆盖本页

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

展示一键命令，并说明任何完整性检查失败都会阻止生成“final”文档。

讲述要点：

- 锁定 episode manifest、run manifest 和 results.parquet
- 保存项目 commit、Arena commit、checkpoint 与场景 SHA256
- 图表和 TeX 表格全部自动生成
- 发布门禁：test 技术报告固定 32 页；PPTX/PDF 固定 30 页
- 发布前执行测试、字体、关系、占位符和隐私审计

## 30. 结论与 Q&A

核心句：PGRR 的核心不是替代经典规划，而是让失败恢复可学习、可约束、可解释

最后再次说明阶段：如果还是 pending，只总结已验证系统和协议，不口头补入未经锁定的数字。

讲述要点：

- 经典规划器保持常态控制
- 特权规划专家降低人工恢复标注成本
- DAgger 覆盖策略诱导的困难恢复状态
- 规划 mask 与有界状态机限制学习策略作用域
- 当前汇报阶段：验证执行中｜数值待锁定
