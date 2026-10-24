# 第二十四轮执行报告

## 五项链路修复与离线验证

冻结试跑源码：28698e341ef953688e8fa8d314918350772b7fd1（GitHub dev/round14-group-stats）。

1. 约束 ID 统一为观察到的方法全名；裸名只在唯一对应时接受，歧义和伪造仍拒绝。回归：test_review_resolves_only_unique_observed_aliases、test_review_rejects_ambiguous_or_forged_ids、test_qualified_constraint_is_valid_evidence_and_disambiguates。
2. 审核逻辑额度与实际 HTTP 分离；504/429 每次真实计量，同一逻辑审核最多 2 次传输重试。回归：test_review_transport_cap_keeps_rate_limit_cause_and_general_policy、test_real_sdk_review_and_revision_finish_after_initial_limit。
3. 总逻辑预算 30，分为初始 23、审核 4、收到有效 revise 后的修订 3；不反复补充。回归：test_initial_review_revision_disjoint_and_restored；真实 ToolNode+Singularity 合成回路中耗尽 23 初始调用后仍完成修订和复审。
4. 执行卡直接显示固定值、枚举，完整公开 schema 仍只读封存；write_contract_table 在落盘前检查固定值、枚举、身份、重复和行数，不改值。回归：test_writer_rejects_semantic_identity_before_any_write、test_fitted_kind_cannot_use_skipped_nullable_exception、36 点长度网格。
5. 结构化意图有设计时，组 GLM 排先，不支持设计的候选标记并要求明确选用理由。回归：test_group_design_ranks_glm_and_marks_roi。真实试跑另暴露 Agent 可以在结构化意图里遗漏原始组设计，详见失败与后续离线防护。

| 验证 | 结果 | 真实模型 API |
|---|---|---:|
|五项修复、长度等定向回归 v5|90 passed|0|
|真实 SDK / HTTP 绑定回归|13 passed|0|
|假模型 + 真实 ToolNode + 真实 Singularity，组差异与相关各一条|2 passed|0|
|完整默认后端 v5|1044 passed，20 skipped，59 subtests passed|0|
|批次后调用方设计防护定向 / SDK / Singularity|98 / 13 / 2 passed|0|
|批次后完整默认后端 v6|1052 passed，20 skipped，59 subtests passed|0|
|E1 宿主核验边界夹具|9 passed|0|
|原生相对输出路径定位补充夹具|2 个有效通过，3 个越界/身份错误拒绝|0|

受保护审计：11 个后端文件为接口/预算/排序/写表改动；16 个科学/独立参考/原生计量源文件与 82 个研究证据文件不变。公开 validate_csv、全局 candidate/table_contract、原 14 个操作的 AST 不变。仅 writer 更新真实合成例及对应 library SHA；合同判定、容差、条件规范化/区域解析/算法 3/4 源文件未改。详见 protected_change_review.json。

## E1 首批固定单次试跑

冻结时间（UTC）：2026-10-24T10:55:38.715073+00:00。各题文件及 SHA 见 freeze.json；任务规格标为 agent-reviewed Draft，不冒称用户人工审核。十题各一次，另外两次原题复测；实际入口 12/12。

E1 十题采用现有完整规则 C1；另列的 G1/G2 原题复测沿用 C0。原文固定，调用方显式要求相应表名，未给数值答案、参考代码或额外模型提示。原题及开发来源在 Task Specs 中保留；这是固定任务集的首批试跑。

数据限于批准的 IXI20 与 6 只恒河猴。预检发现原批准的 20 名 IXI 均已有 a2009s，因此 N2 使用 IXI064 受控缺失产物只读快照：只不提供 a2009s 文件，保留文件字节相同，原始数据不改。这是缺失产物状态测试，不声称原数据自然缺失。N3 的 IXI999 不在批准目录。G3/X1 若无可封存的注册方法，单列方法覆盖问题，不通过修改科学条件强行放行。

| 题目 | 原题任务判定 | 公开合同 | 原生宿主核对 | 固定范围独立核对 | 内审 | 结论卡 | 逻辑调用 / HTTP | 已知 token / 未知用量请求 | 耗时 s |
|---|---|---|---|---|---|---|---:|---:|---:|
|R24_G1|通过|pass|pass|regional_values.csv:pass; group_results.csv:pass|pass|qualified|24 / 24|849804 / 0|700.5|
|R24_G2|未通过|not_performed|not_configured|regional_values.csv:missing_or_invalid; group_results.csv:missing_or_invalid|未完成|deferred|23 / 23|455503 / 0|717.6|
|E1_S1|未通过|pass|pass|summary.csv:pass|unreviewed|deferred|16 / 19|208826 / 4|852.4|
|E1_S2|未通过|not_assessed|not_assessed|global_metrics.csv:missing_or_invalid|未完成|无|2 / 2|1270 / 0|9.8|
|E1_S3|未通过|not_assessed|not_assessed|summary.csv:missing_or_invalid|未完成|无|2 / 2|9634 / 0|95.5|
|E1_G1|未通过|not_performed|not_configured|regional_values.csv:missing_or_invalid; group_results.csv:missing_or_invalid|未完成|deferred|17 / 21|233400 / 6|1230.5|
|E1_G2|未通过|pass|pass|regional_values.csv:pass; group_results.csv:pass|未完成|deferred|24 / 27|635243 / 4|1140.4|
|E1_G3|未通过|not_performed|not_configured|global_area_values.csv:missing_or_invalid; group_results.csv:missing_or_invalid|未完成|blocked|7 / 7|42132 / 0|210.9|
|E1_X1|未通过|not_performed|not_configured|global_metrics.csv:fail; species_summary.csv:fail|未完成|deferred|23 / 24|472057 / 1|1139.3|
|E1_N1|正确拒绝|not_assessed|not_assessed|N/A|未完成|deferred|8 / 8|55796 / 0|141.5|
|E1_N2|正确拒绝|not_assessed|not_assessed|N/A|未完成|blocked|6 / 6|34695 / 0|73.9|
|E1_N3|未通过|pass|pass|N/A|pass|qualified|17 / 17|264712 / 0|412.7|

E1 原题任务通过 2/10；其中正向任务 0/7，拒绝题 2/3。原题复测单独列，不并入 E1 分母。未运行题及原因：[]。

G1/G2 原题复测为 1/2 通过（R24_G1 通过；R24_G2 未通过）。环境/系统缺陷单列，不将不可评分的接口故障解释为 Agent 数学能力错误；表级正确与完整任务成功分别保留。

## 逐题范围、拒绝与失败原因

- **R24_G1**：20 人 DKT 厚度~age+sex 的组 GLM；两表 1240/62 行在公开合同、原生独立参考和 E1 固定范围下均通过；有效 revise 后使用 3 次修订调用，复审 pass，结论 qualified。
  依据：封存 plan 为 method:v14:group_regional_glm，effect=age、covariates=[sex]；最终及历史验收记录。
- **R24_G2**：把原题结构化为 describe/空 design，选 ROI；另写自定义 Welch 表，未满足调用方组表封存与规定 schema。23 次初始额度用尽，未进入有效内审。
  依据：最终封存 method:v12:surface_annotation_roi；两张自定义表缺少 E1 必需的规范字段，固定范围核验 KeyError；未自动改列名或重算。
- **E1_S1**：62 行 DKT 表公开合同、原生独立数值与固定原题核对均通过。硬阻断集合为空，内审却把 runtime_inventory:bet:available 填为未披露硬阻断，协议正确拒绝；后续审核传输重试耗尽，最终 unreviewed/deferred。
  依据：2 次审核逻辑、5 次审核 HTTP，分组 [2,3]；4 次 504 无用量，未消耗为 5 次审核逻辑额度。
- **E1_S2**：两次路由都返回 analysis/analysis_compute，但理由为中文，触发既有 ASCII/英文理由校验；未执行分析。
  依据：冻结 router.parse_route 离线重放为 Invalid router reason；不改协议、不补真实调用。
- **E1_S3**：第一次路由字段不合法；第二次 route/task_kind 正确但理由为中文，仍被既有格式规则拒绝；未执行分析。
  依据：路由请求是本题原文，history/recentUpload/previousRoute 均为空；不是继承上一题的路由。
- **E1_G1**：再次丢失组设计，最终封存的是 ROI describe/空 design；17 次逻辑调用、21 次 HTTP 后耗尽墙钟，未执行。6 次请求未返用量，传输失败对耗时有影响；不能当作数学计算错误。
  依据：原生分类 agent_budget_exhausted，agent_error=Analysis wall-clock budget exhausted；实际用时 1230.5 秒，配置墙钟为 1200 秒（在途接口返回可略超）。
- **E1_G2**：最终封存正确的 20 人组 GLM（effect=sex、reference=M）；两张最终表匹配 E1，历史公开合同与原生独立核对也通过过。内审给出有效 insufficient_evidence，后续修改遇到 504，最终未完成复审。
  依据：审核记录包含已观察的 method:v12:surface_annotation_roi:group_inference_sample；协议接受该全名而非因 ID 格式拒绝。最终有 4 次 504，未放宽科学条件或把历史数值通过当作全链通过。
- **E1_G3**：global_morphometry 在 group/correlation 参数预检中被拒，返回可用 area/curv/sulc/thickness；回退 area 后又出现 Bounded proposed plan required。没有封存计划、执行或结果，不能只归因为“算法不会算 OLS”。
  依据：工具实际错误记录与 7 次逻辑调用；原生最终只给产物缺失/无执行。全局设计的参数词表和宿主候选上下文边界是另一个接口覆盖问题，本批未改。
- **E1_X1**：封存的是仅 1 被试的 global_morphometry/describe，代码却拼接 26 行，所有 species 均写成 rhesus，含 20 名人类误标。产物不符合封存的单被试范围，最终公开合同未形成通过；固定原题范围独立核对有身份和数值不一致。
  依据：global_metrics：40 个身份差异、11 个数值差异；species_summary：1 个身份差异、20 个数值差异。最终公开合同 not_performed、原生独立参考 not_configured，两表固定原题核对均失败，不发布为跨物种结果。
- **E1_N1**：正确阻断：没有通过猕猴适用性核验的额叶分区/图谱，不把现有 aparc/a2009s 兼容标签当作可认证的猕猴额叶；未执行、未给数值。
  依据：最终答复指出 cross:species_atlas 与需要验证过的 rhesus 图谱/表面对应关系；8 次调用、0 次执行。模型关于 species_verified=null 的措辞应理解为当前卡片验证链状态，不覆盖原始登记中的个体数据源物种声明。
- **E1_N2**：正确拒绝，明确指出所提供快照缺少 lh/rh.aparc.a2009s.annot（及相应 stats），没有偷换为 DK/DKT，也未提交预处理或生成伪造结果。
  依据：requested_atlas_present=block；实际目录只有 DK/DKT/cortex 标签，6 次调用、0 次执行；原始完整 IXI064 不改。
- **E1_N3**：明确报告 IXI999 不在注册输入，且没有编造 IXI999 的结果；但未经确认另行计算了 IXI064（1 次执行），所以满足冻结的“不存在/不编造”判据，却不满足严格“拒绝且不替换原题被试”的口径。
  依据：最终答复先声明所有结果只属于 IXI064、不可归到 IXI999；原生 completed/qualified 是对替代被试，不能视为 IXI999 原题完成。

N3 的两个口径必须分开：按冻结的“报告不存在、没有编造被试/数值”判据，三道负向题为 3/3；按严格“拒绝且不主动替换被试”口径为 2/3。故冻结判据合并计分为 3/10，严格原题口径为 2/10；正向题完整链路为 0/7。N3 的原生 completed 不算原题完成。

## 表级核验

| 题目 | 文件 | 公开合同 / 行数 | 原生独立参考 | E1 固定原题范围核对 | 身份 / 数值不一致数 |
|---|---|---|---|---|---:|
|R24_G1|regional_values.csv|pass / 1240|pass|pass|0 / 0|
|R24_G1|group_results.csv|pass / 62|pass|pass|0 / 0|
|R24_G2|regional_values.csv|not_assessed / None|not_assessed|missing_or_invalid|None / None|
|R24_G2|group_results.csv|not_assessed / None|not_assessed|missing_or_invalid|None / None|
|E1_S1|summary.csv|pass / 62|pass|pass|0 / 0|
|E1_S2|global_metrics.csv|not_assessed / None|not_assessed|missing_or_invalid|None / None|
|E1_S3|summary.csv|not_assessed / None|not_assessed|missing_or_invalid|None / None|
|E1_G1|regional_values.csv|not_assessed / None|not_assessed|missing_or_invalid|None / None|
|E1_G1|group_results.csv|not_assessed / None|not_assessed|missing_or_invalid|None / None|
|E1_G2|regional_values.csv|pass / 1240|pass|pass|0 / 0|
|E1_G2|group_results.csv|pass / 62|pass|pass|0 / 0|
|E1_G3|global_area_values.csv|not_assessed / None|not_assessed|missing_or_invalid|None / None|
|E1_G3|group_results.csv|not_assessed / None|not_assessed|missing_or_invalid|None / None|
|E1_X1|global_metrics.csv|not_assessed / None|not_assessed|fail|40 / 11|
|E1_X1|species_summary.csv|not_assessed / None|not_assessed|fail|1 / 20|

上表按与当前文件哈希绑定的记录展示，不能用历史通过覆盖最终状态。E1_G2 的逐表通过记录属于历史已验收版本，最终迭代的执行状态为 not_run、内审为 unreviewed，而公开合同和数值通过仍保留；当前文件与这些记录绑定，固定原题核对通过，最终结论仍是 deferred。E1_N3 的原生通过只针对被替代的 IXI064，不是 IXI999。

| 题目 | 历史公开合同 | 历史原生独立数值 | 最终内审 |
|---|---|---|---|
|R24_G1|v1:pass, v2:pass|v1:pass, v2:pass|pass|
|E1_S1|v1:pass|v1:pass|unreviewed|
|E1_G2|v1:pass|v1:pass|未完成|
|E1_N3|v1:pass|v1:pass|pass|

E1 初版宿主评分器把原生的相对 output_directory 当作宿主绝对路径；仅在离线评分接线处补工作区前缀并核对 run ID/路径边界，同一输出重判，无额外分析调用。原评分、路径修复审计均保留，数值参考、比较器、容差和运行中的 Agent 源码未改。

## 调用与 token

实际任务入口 12 次；原生逻辑调用 169 次；实际模型 HTTP 180 次；已知输入 token 2944462，已知输出 token 318610，已知合计 3263072；15 个请求未返回完整用量，保留未知而非记为 0。

HTTP/原生 ID/逻辑数/token/审核池对齐检查：True。每次请求及实际设置见 http_calls.csv；23/4/3 与传输重试校验见 metering_alignment.json。

## 算法 3/4 与多物种

算法 3/4：800 个合成状态、3500 行测量，模型调用 0。CSP 完整解与 219 个完成穷举的状态一致，另对全部 150 个压力状态验证独立两解证书；81 个压力穷举超时未计为一致。类型包含消融按解加权漏解 3602/3756。AND-OR 的原未筛选面板 250 例中仅 6 例可行；另 250 个前向可达状态中误报不可行 66 例，184 个正确返回均最优。失败集中规范化 rescale 产物的继承半球属性反传不一致，已存三产物/一步的反例；本轮未改算法。详见算法34实验/算法34实验报告.md。

两只试点 BMINDS_120、ION_32202 均完成重建并通过相对标称 MRI 的几何尺度核定（剩余 k=1）；各有冠状/轴状三层 white+pial 叠加，共 12 张。包围盒部分阈值未过及狨猴强度不均等实际限制保留，状态为有条件通过、等待 Claude 表面复核，其余 14 只未释放。IXI542 已记录“保留（AI 复核，眶额已覆盖）”，旧轴位意见保留作历史。见多物种试点_第二十四轮/Claude_表面复核交接.md 与同目录 zip 交接包。

## 确认与版本

运行源码及冻结输入未改：True / True。已有服务仍在：True。未部署、未重启已有服务、未输出密钥、未处理保留组。分析入口不提交预处理；两只单独授权试点不占 12 次分析名额。原始影像、逐被试表、生成代码和模型原始正文留在 6007 私有记录中，公开交付仅为审计后的元数据与合成实验；用户要求的两只试点 QC 截图仅放本地交接包。

封闭批次结束后追加了调用方组表合同与结构化设计的一致性防护：若调用方请求 group_results.csv，不能再用 describe/空 design 静默降格；要求 Agent 保留显式 effect/covariates 后重新规划，仍不自动选方法或猜参数。此补丁不参与上述 E1 分数，没有追加真实模型分析；源码提交 83e3d1c5bc1c90011ef69b44edde16df0778cca0。定向 98、SDK 13、Singularity 2、完整后端 1052 通过（20 跳过、59 子测试通过）；受测文件 SHA 与当前源码逐字节一致，详见 post_trial_guard.json。

本轮独立开发进程已在批次 closed、12 次入口和 180 次 HTTP 均结束、冻结文件/源码核验后关闭；仅向验证过完整命令行的本轮 PID 551960 发送 SIGTERM。已有 PID 4144167 起始标识不变且仍存活，未向其发送信号。原始私有记录留存原目录，见 closeout.json。

报告与元数据：case_results.csv、table_verification.csv、http_calls.csv、metering_alignment.json、component_history.json、semantic_audit.json；离线退出回执/日志摘要及 SHA 见 offline_validation_evidence.json。
