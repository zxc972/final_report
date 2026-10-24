# 第二十三轮执行报告

分项报告：[算法2补实验](region_resolution_v2_zh.md) · [条件规范化正式评测](condition_canon_test_v2_zh.md)。逐次证据见[审计目录](https://github.com/zxc972/final_report/tree/dev/round14-group-stats/results/round23_20261024/report)。

已完成本轮修复、算法2补实验与测试集v2正式评测。按原题实际运行6次，严格按原题范围全链通过1次；以下保留每次成功、失败及停跑依据。运行代码封存于`1767b2179959352170a81d0dbf90e6ae9267f014`，启动前已推送并核对GitHub分支`dev/round14-group-stats`。

## 1. 四项修复与离线门禁

| 修复 | 行为与验证 |
|---|---|
| 执行说明 | 卡片改为指向只读INPUTS.md、合同schema和封存JSON。20/100/200名×62/124分区×1/2/3指标，18组分析+18区域分析的36项长度回归及单被试/人类全局/猕猴合成全局覆盖；剩余超长为system_defect，保留实际计费但免除相应规划配额，同类两次即停。反思仅在开放工具时要求。 |
| 审核预算 | 总预算30内保护4个审核尝试额度，非审核最多26（含路由）；协议、504与兼容重试均占审核池；实际逻辑/HTTP计量不清零、不借给编码。 |
| 表格写出 | ops.write_contract_table按封存文件名、列名、列顺序写UTF-8逗号CSV，带表头、无索引。只做序列化，不算统计、不映射别名、不修数字。合同失败附实际表头/分隔符/文件名，判断规则不变。真实Agent可不用。 |
| 失败分类 | system_defect、agent_budget_exhausted、review_incomplete、contract_failed分别报告，并保留传输/权限等独立原因。纯上游传输故障不计模型连续失败停跑。 |

全量默认后端：**1031 passed、18 skipped、59 subtests passed**。定向82项、兼容51项、真实SDK绑定13项通过；脚本化假模型+真实ToolNode+真实Singularity的G1/G2合成回路各1次通过，卡片859字符，文件在容器内只读，辅助函数写表通过公开合同与宿主核对。门禁付费模型调用0。本轮新增的两项容器测试为opt-in，已在独立门禁显式执行；默认套件的18项skip仍按原结果保留。

受保护审计：21个后端文件按上述接口修复有意改变；18个科学实现/计量源与82个research_v13文件保持；旧14个操作函数AST及样例保持；公开validate_csv判断AST、全局候选/合同、宿主数值参考及容差保持。operation_examples只新增真实合成写表回执及库SHA。模型调用器仅新增显式1500授权上限参数，旧默认1200与complete调用逻辑保留。逐文件理由见仓库`agent/experiments/round23/PROTECTED_CHANGES.md`及`offline/protected_review.json`。

### 回归名称与结果

以下测试均在真实分析入口开放前通过；文件位于agent/modules/agent/tests。

| 测试文件/名称 | 结果 |
|---|---|
| test_round23_system_repairs.py::test_execution_card_length_grid | 36个组合通过，组卡≤1500、其他卡≤2200字符 |
| test_round8_closure.py::test_bounded_returns_and_complete_recoverable_file / test_round15_global_method.py::test_discovery_types_and_bounded_card / test_macaque_global_acceptance.py::test_planner_seals_direct_macaque_inputs_without_stats | 单被试、人类全局、猕猴合成全局卡片≤1500字符，通过 |
| test_residual_overflow_is_host_defect_and_planning_refund_retains_actual_calls | 同一宿主缺陷两次停止，实际计量保留，规划仅豁免一次 |
| test_real_toolnode_no_unavailable_reflection_on_host_failure | 真实ToolNode中未开放反思时不要求反思，通过 |
| test_contract_writer_roundtrip_and_strict_failures / test_delimiter_diagnostics_do_not_change_validation | 往返与严格拒绝通过；tab/分号两种诊断通过 |
| test_review_reserve_cannot_be_borrowed_and_persists | 非审核26次不能借保护池，审核4次持久化，通过 |
| test_reserved_real_sdk_nonjson_revise_504_rereview_after_coding_limit | 编码额度用尽后，非JSON→revise→504→pass的4次审核HTTP完成，通过 |
| test_distinct_failure_categories_have_evidence | 四类失败参数化用例通过 |
| test_round23_full_sandbox.py::test_round23_guidance_writer_real_container | correlation/group两种真实容器回路通过（2项） |
| test_round23_condition_eval.py / test_round23_batch_control.py | 授权恢复、冻结与分层重采样、停跑规则通过，计入定向82项 |
| test_round21_sdk_http_observer.py | SDK/原生计量绑定13项通过 |

## 2. 原题复测

G1：这 20 名 IXI 被试，DKT 各分区平均皮层厚度与年龄的关系，控制性别。

G2：比较这 20 名 IXI 被试中男性和女性的 DKT 各分区平均皮层厚度。

保持第22轮配置：auto、product_graph_planner、C关闭、deepseek-v4-pro，模型30/工具60/执行8/单次执行及整体墙钟1200秒，外层最多3轮；本轮仅把总模型额度内的4个保护给审核。每次全新会话，代码/阈值/配置在批内不变，没有人为提供针对这两道原题的分析程序或数值答案；提供的均为登记元数据与通用读取、统计和序列化接口。

“原题全链”同时要求：原生完成、两张指定表均通过公开和宿主核对、正确DKT全部62分区/厚度/n20/原题设计、内审有效pass。保留原生full_chain字段及选中计划，避免把其他方法的整体pass误记成指定表已通过。qualified/deferred按原规则记录。

| 次序 | 原生状态 | 原题全链 | 逻辑调用 | HTTP | 已知输入token | 已知输出token | 无usage尝试 | 执行 | 秒 | 内审 | 结论卡 | 失败分类 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| R23_G1_1 | completed | 通过 | 13 | 15 | 344903 | 30826 | 2 | 1 | 689.5 | pass | qualified | 无 |
| R23_G1_2 | failed | 未通过 | 21 | 25 | 329153 | 29560 | 5 | 0 | 1162.9 | not_performed | deferred | agent_budget_exhausted |
| R23_G1_3 | incomplete_review | 未通过 | 16 | 16 | 579002 | 36608 | 0 | 1 | 571.1 | unreviewed | deferred | review_incomplete |
| R23_G2_1 | failed | 未通过 | 27 | 28 | 713925 | 35458 | 1 | 2 | 787.9 | revise | deferred | review_incomplete |
| R23_G2_2 | failed | 未通过 | 25 | 28 | 441222 | 38345 | 4 | 1 | 1149.4 | not_performed | deferred | contract_failed |
| R23_G2_3 | incomplete_review | 未通过 | 17 | 19 | 573037 | 32075 | 2 | 1 | 840.6 | unreviewed | deferred | review_incomplete |

实际分析入口6次；上游HTTP 131次；已知输入/输出token为2981242/202872，另14次无usage，不能视为零消耗。全部完成案例的HTTP、原生attempt/logical ID、token、未知usage均逐项一致；unmetered为0。

### 阶段、审核池与阻塞依据

- **R23_G1_1**：unplanned → planned → sealed → executed_ok → finalized。选中方法`method:v14:group_regional_glm`；设计`{"covariates": ["sex"], "effect": "age", "reference": null}`；非审核12/26，审核逻辑/HTTP=1/3，合计预算单位15/30。
  执行源码回收1/1，均按原生执行SHA关联；其中0份已执行源码引用辅助写表函数（仅静态引用观察，不宣称分支覆盖）。
- **R23_G1_2**：unplanned → planned → sealed。选中方法`method:v12:surface_annotation_roi`；设计`null`；非审核21/26，审核逻辑/HTTP=0/0，合计预算单位21/30。
  判定：Agent logical/non-review or planning-stage allowance was exhausted without a recorded host defect；终态证据：`{"status": "not_executed", "error": "No Python execution in this iteration", "agent_error": "Analysis wall-clock budget exhausted", "automatic_finalization": null}`。
  执行源码回收0/0，均按原生执行SHA关联；其中0份已执行源码引用辅助写表函数（仅静态引用观察，不宣称分支覆盖）。
- **R23_G1_3**：unplanned → planned → sealed → executed_ok → finalized。选中方法`method:v14:group_regional_glm`；设计`{"covariates": ["sex"], "effect": "age", "reference": null}`；非审核14/26，审核逻辑/HTTP=2/2，合计预算单位16/30。
  判定：A final valid passing internal review was not completed; inspect protocol, transport and protected review-budget counters；终态证据：`{"status": "success", "error": null, "agent_error": null, "automatic_finalization": {"status": "finalized", "artifact_receipt_id": "f139828a1f014477b120311e116c5d3e", "manifest_sha256": "18feb863f772efbee52bb2f550336934fb7ec578f911c98eda0e8ab062a7eb83"}}`。
  内审协议：{"expected_constraint_ids": ["group_inference_sample"], "failed_attempts": [{"attempt": 1, "protocol_error": "Disclosure must cite observed hard-block ids", "returned_undisclosed_constraint_ids": ["method:v12:surface_annotation_roi:group_inference_sample"]}, {"attempt": 2, "protocol_error": "Disclosure must cite observed hard-block ids", "returned_undisclosed_constraint_ids": ["method:v12:surface_annotation_roi:group_inference_sample"]}]}。
  执行源码回收1/1，均按原生执行SHA关联；其中1份已执行源码引用辅助写表函数（仅静态引用观察，不宣称分支覆盖）。
- **R23_G2_1**：unplanned → planned → sealed → executed_ok → executed_failed → sealed → executed_ok → finalized → executed_failed。选中方法`method:v14:group_regional_glm`；设计`{"covariates": [], "effect": "sex", "reference": "F"}`；非审核26/26，审核逻辑/HTTP=1/2，合计预算单位28/30。
  判定：A final valid passing internal review was not completed; inspect protocol, transport and protected review-budget counters；终态证据：`{"status": "success", "error": null, "agent_error": null, "automatic_finalization": {"status": "finalized", "artifact_receipt_id": "daa425495239461ebdd089d7a66bc7cf", "manifest_sha256": "18feb863f772efbee52bb2f550336934fb7ec578f911c98eda0e8ab062a7eb83"}}`。
  执行源码回收2/2，均按原生执行SHA关联；其中2份已执行源码引用辅助写表函数（仅静态引用观察，不宣称分支覆盖）。
- **R23_G2_2**：unplanned → planned → sealed → executed_ok → executed_failed。选中方法`method:v14:group_regional_glm`；设计`{"covariates": [], "effect": "sex", "reference": null}`；非审核25/26，审核逻辑/HTTP=0/0，合计预算单位25/30。
  判定：Public columns, fixed values, identities or row count did not pass；终态证据：`{"status": "not_executed", "error": "No Python execution in this iteration", "agent_error": "Analysis wall-clock budget exhausted", "automatic_finalization": null}`。
  执行源码回收1/1，均按原生执行SHA关联；其中1份已执行源码引用辅助写表函数（仅静态引用观察，不宣称分支覆盖）。
- **R23_G2_3**：unplanned → planned → sealed → executed_ok → finalized。选中方法`method:v14:group_regional_glm`；设计`{"covariates": [], "effect": "sex", "reference": "M"}`；非审核15/26，审核逻辑/HTTP=2/4，合计预算单位19/30。
  判定：A final valid passing internal review was not completed; inspect protocol, transport and protected review-budget counters；终态证据：`{"status": "success", "error": null, "agent_error": null, "automatic_finalization": {"status": "finalized", "artifact_receipt_id": "007fa5e5ae1949f69cf5985345a3dd0a", "manifest_sha256": "18feb863f772efbee52bb2f550336934fb7ec578f911c98eda0e8ab062a7eb83"}}`。
  内审协议：{"expected_constraint_ids": ["group_inference_sample"], "failed_attempts": [{"attempt": 1, "protocol_error": "Review finding cites unavailable evidence", "returned_undisclosed_constraint_ids": ["group_inference_sample"]}, {"attempt": 2, "protocol_error": "Disclosure must cite observed hard-block ids", "returned_undisclosed_constraint_ids": ["method:v12:surface_annotation_roi:group_inference_sample"]}]}。
  执行源码回收1/1，均按原生执行SHA关联；其中1份已执行源码引用辅助写表函数（仅静态引用观察，不宣称分支覆盖）。

已核实的残余问题：G1_2未完成正确组设计选择，在执行前耗尽墙钟预算；G1_3的两次审核均返回带方法前缀的约束ID，而审核协议要求裸ID，当时尚余2个审核额度；G2_1得到有效revise后，非审核26次额度已满，不能继续修订。后两者保留为review_incomplete。G2_2的group_results.csv虽有62行且逗号/表头正确，但effect_size_kind不在封存枚举内，未能完成修复，随后耗尽墙钟；该类别保留为contract_failed，宿主数值检查未执行。G2_3两张表均核对通过，内审先后因引用不可用证据、带方法前缀的约束ID而失败；另2次504使4个审核HTTP额度全部用完。协议、披露及合同规则均未放宽。


### 两张表逐次核对

身份差异与数值差异分列；“未核对”保留空值，不替换为0，也不沿用其他文件的整体pass。

| 案例 | 表 | 公开合同 | 行数/预期 | 宿主状态 | 身份差异 | 数值差异 | 已核对标量 |
|---|---|---|---|---|---:|---:|---:|
| R23_G1_1 | regional_values.csv | pass | 1240/1240 | pass | 0 | 0 | 6200 |
| R23_G1_1 | group_results.csv | pass | 62/62 | pass | 0 | 0 | 682 |
| R23_G1_2 | regional_values.csv | not_assessed | 未核对/未核对 | not_assessed | 未核对 | 未核对 | 未核对 |
| R23_G1_2 | group_results.csv | not_assessed | 未核对/未核对 | not_assessed | 未核对 | 未核对 | 未核对 |
| R23_G1_3 | regional_values.csv | pass | 1240/1240 | pass | 0 | 0 | 6200 |
| R23_G1_3 | group_results.csv | pass | 62/62 | pass | 0 | 0 | 682 |
| R23_G2_1 | regional_values.csv | pass | 1240/1240 | pass | 0 | 0 | 6200 |
| R23_G2_1 | group_results.csv | pass | 62/62 | pass | 0 | 0 | 682 |
| R23_G2_2 | regional_values.csv | pass | 1240/1240 | not_assessed | 未核对 | 未核对 | 未核对 |
| R23_G2_2 | group_results.csv | fail | 62/62 | not_assessed | 未核对 | 未核对 | 未核对 |
| R23_G2_3 | regional_values.csv | pass | 1240/1240 | pass | 0 | 0 | 6200 |
| R23_G2_3 | group_results.csv | pass | 62/62 | pass | 0 | 0 | 682 |

完整时序`stages.csv`、请求/计量`http_attempts.csv`与`meter_alignment.json`、每次结论卡/失败/计划/执行源码SHA在`report/`；逐被试表和原始请求响应、执行源码保留在6007私有归档；本地仅同步24个经过SHA核对的公开报告文件。

## 3. G1方向与历史观察

| 本轮案例 | 分区/FDR家族 | q<.05 | 负向年龄系数 | d_min | df | 内审 |
|---|---:|---:|---:|---:|---|---|
| R23_G1_1 | 62/62 | 32 | 58/62 (93.55%) | 0.645006370 | [17] | 已通过 |
| R23_G1_2 | 未核对 | — | — | — | — | — |
| R23_G1_3 | 62/62 | 32 | 58/62 (93.55%) | 0.645006370 | [17] | 未完成 |

以下仅取本轮R23_G1_1的已核对表作方向观察，没有合并历史运行或重新拟合。系数单位为存储厚度（软件约定mm）/年。

| DKT观察集合 | 半球分区数 | 负系数数 | FDR显著数 | 平均年龄系数 | 平均绝对系数 |
|---|---:|---:|---:|---:|---:|
| 额上及额下 | 8 | 8 | 7 | -0.00519107 | 0.00519107 |
| 颞上 | 2 | 2 | 0 | -0.00244047 | 0.00244047 |
| 下颞 | 2 | 2 | 0 | -0.00317345 | 0.00317345 |
| 内侧颞（单独观察） | 4 | 3 | 0 | -0.00197213 | 0.00298547 |
| 前扣带 | 4 | 4 | 1 | -0.00408754 | 0.00408754 |

本轮多数系数为负，符合文献变薄的大方向；区域强弱排序并不相同，不能把未显著等同于保留，也不把这一小样本当作复现验证。

d_min来自封存宿主设计：双侧alpha=.05、power=.8的正态近似标准化连续斜率，未作FDR后的效力解释。n20、未控制站点/扫描仪与AI筛查局限均保留；不为达到显著或更高结论等级改规则。

文献对照只描述方向。[Fjell等2009](https://pubmed.ncbi.nlm.nih.gov/19150922/)在6样本883人中报告广泛年龄相关变薄，额上/额下及颞叶上部效应较强。摘要对相对少受影响的表述为“下颞叶和前扣带”；第十九轮指令提到内侧颞叶，因此这里分别提供下颞与内侧颞观察，不把两者混用，也不把DKT单一区域当作颞顶交界的精确映射。逐区域方向、显著数及平均系数见`g1_direction_summary.json`；不据此声称复现效应排序或因果关系。

第二十二轮G1_1单列为历史“已核对、未完成内审”：32/62分区FDR显著、58/62负向、d_min=.6450063705；未并入本轮次数、通过率或本轮科学结论。第二十二轮G1_2/G2_2/G2_3的13/14/13个重复宿主超长错误已更正为system_defect；原始归档/计量不变，另存更正summary和证据。

## 4. 算法2补实验

已完成fsaverage+IXI20：82个临时分类任务、126个条件/半球记录、无跳过，原始输入变化0、模型调用0。使用recon-all7.2默认2016版DK/CD/DKT GCS，未采用可选2020 DKT。完整文件名/SHA、回执、所有方法C1/C2错误、C3分布、稳定性及θ=.3–.8敏感性见`第二十三轮_算法2补实验.md`及`region_resolution_v2/`。

加权方法：C1被试准确率中位数100%、最小98.39%，3个边界标签错分；C2全部100%。C3在20人×2半球×6区的240个观察中，Dice中位数.852180、最小.477541；相对fsaverage映射一致率按被试平均半球后中位数.972973、最小.959459。非加权C1为2个错误，C3中位数.852567；不按结果调整权重、关键词或阈值。

## 5. 条件规范化测试集v2

标准答案83条（15可执行/68建议性）与交接包ID/原文引文一致，零修改；冻结时间2026-10-24 06:44:39.981925 UTC。SHA-256：`2ca5ca7492d9f09569372085a0cf75715d41a8e78e8bd24a0fc5c38015d84e3e`。7个待决定按文件计分并给敏感性；v1预测不重跑，合并128条、24可执行。

| 数据 | 组 | 模板准确率 | 可执行F1 | 非可执行F1 | 规范键F1 | 审核队列 |
|---|---|---:|---:|---:|---:|---:|
| v2 83 | full_v2 | 78.31% | 50.00% | 89.86% | 25.00% | 14 |
| v2 83 | k1_v2 | 79.52% | 51.43% | 87.02% | 26.67% | 6 |
| v2 83 | direct_v2 | 79.52% | 61.54% | 88.19% | 0.00% | 0 |
| v2 83 | retrieval_only | 10.84% | 31.25% | 5.71% | 0.00% | 0 |
| 合并128 | full_v2 | 81.25% | 54.55% | 90.57% | 40.00% | 15 |
| 合并128 | k1_v2 | 81.25% | 56.60% | 88.67% | 41.67% | 7 |
| 合并128 | direct_v2 | 80.47% | 62.07% | 88.89% | 0.00% | 0 |
| 合并128 | retrieval_only | 11.72% | 32.43% | 7.41% | 0.00% | 0 |

全部P/R/F1、每项95%区间、分层bootstrap2000次（种子20261023）、精确McNemar及排除7条/合并排除13条结果，见`第二十三轮_条件规范化正式评测.md`及`condition_canon_test_v2_results/`。full的21条错误逐条列陈述、标准、预测、原因。算法/提示/词表/default不变，未根据错误调参。

581采样槽位全部拿到回答，共596次HTTP（12次429、3次504），已知token1,171,096，失败15次无usage。截断0、补采槽位0、不可用槽位0。虽请求关闭思考，76个响应仍有reasoning字段，2个报告正reasoning_tokens合计1456；保留该实际观察，没有换参数或丢弃样本。独立审核332预测/596提示/220区间/10精确检验均通过，审核新增HTTP0。

## 6. 停跑与确认

授权上限6次，本次实际6次；未使用余量0。每题最多3次，连续同类可归因链路2次或同题2次系统缺陷即停；每题前两次失败类别均不同，第三次继续条件经冻结控制器重算成立；完成各3次后达到上限。authorization、batch_completed及逐次分类均保留。

本轮没有输出密钥，没有部署或重启已有服务，没有处理保留组IXI117及102311/105216，没有新放行猕猴，没有预处理队列提交。仅执行了第四节明确授权的临时annot实验。10个已有服务指纹均不变；本轮新开发实例已单独停止，8123已关闭；244个冻结运行源文件保持。预处理提交函数在本实例绑定为禁止；审计中的blocked_marker为false，是因为该标记仅在尝试提交时产生，本轮未触发该入口。

付费模型HTTP总数＝条件评测596＋真实分析131＝727；其余离线门禁、算法2、重放与报告均为0。原生逻辑次数与HTTP次数分开，失败无usage不按0处理。运行源提交见本报告首段；结果提交号为本文件所在Git提交，本地完整交付回执另存于知识图谱/round14。
