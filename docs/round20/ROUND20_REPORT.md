# 第二十轮执行报告（2026-10-24）

算法基线为 bundle 提交 `0f22d972a77c968fb610132ccaf2f0931f853254`，已并入主线；与第二十一轮修正合并后的真实复测冻结在 `3b61d7ca1b1493a0fd22c4a75d1cc9e08573b0d8`。本轮区域接入使用另一份 `round20_source` 开发检出，未修改正在复测的 `round22_source`。最终推送号见第二十二轮交付记录。

## 合入、测试与受保护文件

6007 上最终验证：默认后端 **974 passed、16 skipped、59 subtests passed**；区域算法 8 项、区域接入及抽取脚本 10 项、实际 SDK/httpx2 绑定 13 项、合并链路定向回归 48 项均通过。脚本化假模型 + 真实 ToolNode + 真实 Singularity 的 G1/G2 合成回路 2 项通过；这些验证没有调用付费模型。记录见 `evaluation/round20_validation/`。

既有后端只修改 `analysis_lobar_mapping.py`、`analysis_product_planner.py`、`analysis_independent_numeric.py`、`analysis_crossspecies.py`，新增 `analysis_region_overlap.py`。四处修改分别用于叶名解析入口、绑定与封存三类文件、宿主复算、结论披露。不能声称这四个文件摘要不变。原区域算法文件逐字节不变，独立统计比较函数 `compare_rows` / `reference_rows` 的 AST 以及 ATOL/RTOL 不变；现有知识配置与 research_v13 均未修改。逐文件 SHA 及本地/6007 对齐证据见 `evaluation/round20_validation/protected_review.json`。

## 模板与缺失情况

只读容器 `/data/xuancheng/PrimateX_1_7.sif` 的 `/opt/freesurfer-7.2.0/subjects`。仅 fsaverage 存在；fsaverage6、fsaverage5、bert 不存在。fsaverage 左右半球各有 10 个 annot：aparc、aparc.a2009s、aparc.a2005s、oasis.chubs、4 个 PALS_B12 与 2 个 Yeo2011。完整文件名见 `evaluation/round20_validation/template_inventory.json`。其中没有 DKT annot。

C1 DK→DKT、C2 DKT→DK 均无可评组合，准确率和错误标签记 N/A；没有把缺失记成 0 分，也未补造 annot。运行器的 skipped 共 8 条：fsaverage 左右缺 DKT，另三个主体左右均缺 surface 或 DK annot。C3 可评 fsaverage 左右各 74 个 Destrieux 标签；原始结果完整保存在 `evaluation/region_resolution/region_resolution_results.json`。不同分辨率的 stability 为空，解释为 not_assessable，不能推断一致或不一致。

## C3 几何结果

以下均值对 6 个叶 × 2 个半球的 Dice 取平均；没有官方语义金标准，不把这些数称为准确率。

| 方法 | 平均 Dice | 最小 Dice | 已分配标签 / 148 |
|---|---:|---:|---:|
| overlap_weighted | 0.813008 | 0.633023 | 146 |
| overlap_unweighted | 0.812533 | 0.633023 | 144 |
| name_exact | 0.000000 | 0.000000 | 0 |
| keyword | 0.674448 | 0.509741 | 104 |

面积加权默认结果共 4/12 个叶为 resolved，8/12 为 qualified；包括覆盖率和纯度都较高、但仍受歧义标签影响而 qualified 的左额叶。逐叶值如下。

| 半球 | 叶 | cov | pur | Dice | verdict |
|---|---|---:|---:|---:|---|
| lh | cingulate | 0.600080 | 0.855162 | 0.705265 | qualified |
| lh | frontal | 0.939860 | 0.905459 | 0.922339 | qualified |
| lh | insula | 0.628676 | 0.700606 | 0.662695 | qualified |
| lh | occipital | 0.860530 | 0.862714 | 0.861620 | resolved |
| lh | parietal | 0.769991 | 0.930553 | 0.842692 | qualified |
| lh | temporal | 0.962620 | 0.852907 | 0.904448 | qualified |
| rh | cingulate | 0.619664 | 0.832504 | 0.710486 | qualified |
| rh | frontal | 0.958962 | 0.888351 | 0.922307 | resolved |
| rh | insula | 0.569521 | 0.712462 | 0.633023 | qualified |
| rh | occipital | 0.878396 | 0.840896 | 0.859237 | resolved |
| rh | parietal | 0.765566 | 0.901988 | 0.828197 | qualified |
| rh | temporal | 0.961453 | 0.852650 | 0.903789 | resolved |

默认 θ=0.5、κ=0.8、π=0.8、τ=0.2 均保持 bundle 原值；未调整关键词表。θ 敏感性仅记录，不据此选择新默认值。

| θ | LH 未分配 | LH 平均 Dice | LH resolved | RH 未分配 | RH 平均 Dice | RH resolved |
|---:|---:|---:|---:|---:|---:|---:|
| 0.3 | 0 | 0.816315 | 3 | 0 | 0.809506 | 3 |
| 0.4 | 1 | 0.816676 | 2 | 0 | 0.809506 | 3 |
| 0.5 | 2 | 0.816510 | 1 | 0 | 0.809506 | 3 |
| 0.6 | 10 | 0.783155 | 0 | 9 | 0.764424 | 0 |
| 0.7 | 14 | 0.756023 | 0 | 13 | 0.750330 | 0 |
| 0.8 | 22 | 0.720076 | 0 | 21 | 0.715188 | 0 |

Destrieux 对照表为 `evaluation/region_resolution/destrieux_label_table.csv`，148 行，含归属、最大/次大包含度及关键词归属，按最大包含度升序。summary 和标签表已复制到 `知识图谱/round14/region_resolution/`。

## Agent 接入

人类 + 请求叶名 + aparc.a2009s 时，读取同一被试同一半球 DK annot、Destrieux annot 和 white，在真实网格上调用原 `resolve_request`。先核对网格顶点数、物理根目录与文件绑定，再封存三文件 SHA、mapping/算法 SHA、cov/pur/Dice、歧义及阈值。新增 DK 参照 annot 的显式网格绑定，保留已有网格门禁。缺 DK/white、网格不一致或无法解析均报告缺失；DK/DKT 官方名称路径及非人类拒绝路径保留。

宿主核对重新检查文件身份、SHA、协议和区域标签，并复算几何证据。**区域映射复算复用同一个区域算法，明确标记 independent_implementation=false；这部分不是独立实现。** 原 ROI/组统计的独立数值参考不变。qualified 的结论卡同时具有 cov/pur 结构字段和文字披露，原判定上限规则不变。

新增测试覆盖 region_overlap 证据、封存三个文件、缺 DK/white、猕猴拒绝、SHA/指标篡改、网格不一致，以及 qualified/resolved 结论披露。

## 独立测试集 v2（待盲标）

保持 v1 的卡片 schema、PROMPT、字段、SourceText 与逐字校验逻辑；原抽取模型 deepseek-v4.1-flash、温度 0.7、thinking disabled、JSON object、max_tokens=8192。objective 对所有方法完全相同，未写模板或答案。仅新增官方来源/方法清单、共享 150 次硬上限和第二批 ID。

LGI 官方 URL 因开发集已用而排除，使用 mris_ca_label；主批只产生 62 条候选，随后按预设备选补入 surface-resample 与 FIRST。共 9 个方法、10 个官方来源，归一化 URL 与开发集/test v1 无交集；原始文档及源清单摘要保留。来源如下：

- `fs_anatomical_stats`：[官方原文](https://surfer.nmr.mgh.harvard.edu/fswiki/mris_anatomical_stats)
- `fs_segstats`：[官方原文](https://surfer.nmr.mgh.harvard.edu/fswiki/mri_segstats)
- `fs_preproc`：[官方原文](https://surfer.nmr.mgh.harvard.edu/fswiki/mris_preproc)
- `fs_surf2surf`：[官方原文](https://surfer.nmr.mgh.harvard.edu/fswiki/mri_surf2surf)
- `wb_metric_resample`：[官方原文](https://www.humanconnectome.org/software/workbench-command/-metric-resample)
- `ants_thickness_script`：[官方原文](https://raw.githubusercontent.com/ANTsX/ANTs/main/Scripts/antsCorticalThickness.sh)
- `ants_thickness_outputs`：[官方原文](https://github.com/ANTsX/ANTs/wiki/antsCorticalThickness-and-antsLongitudinalCorticalThickness-output)
- `fs_ca_label`：[官方原文](https://surfer.nmr.mgh.harvard.edu/fswiki/mris_ca_label)
- `wb_surface_resample`：[官方原文](https://www.humanconnectome.org/software/workbench-command/-surface-resample)
- `fsl_first`：[官方原文](https://fsl.fmrib.ox.ac.uk/fsl/docs/structural/first.html)

| 方法 | 卡片保留陈述 | 盲标候选 | 隔离 |
|---|---:|---:|---:|
| independent_v2_fs_anatomical_stats | 20 | 6 | 0 |
| independent_v2_fs_segstats | 23 | 10 | 0 |
| independent_v2_fs_preproc | 24 | 11 | 0 |
| independent_v2_fs_surf2surf | 14 | 6 | 0 |
| independent_v2_wb_metric_resample | 19 | 7 | 0 |
| independent_v2_ants_thickness | 31 | 17 | 1 |
| independent_v2_fs_ca_label | 15 | 5 | 0 |
| independent_v2_wb_surface_resample | 19 | 8 | 0 |
| independent_v2_fsl_first | 26 | 13 | 0 |

**191 条保留陈述逐字及范围核对通过，1 条保持隔离；交接包选取 83 条，ID 2001–2083。** 按 v1 相同选取字段粗计：inputs 33、conditions 24、checks 11、exceptions 15；仅 inputs 已达到 ≥30 的输入/输出/软件要求目标，这不是可执行性标注。源范围审查修改 115 条（交接条目 55、其余卡片 60），只补全截断原文或收窄陈述；原卡、原始主批/补批冻结文件及逐项 before/after 均保留。

官方 mri_surf2surf 页面关于 paint 输出路径的两段原文存在表述差异（2032/2033）；保留两条及歧义说明给标注者，不做专家判定。sources 交接副本只将换行统一为 UTF-8 LF，所有引文/字符偏移/摘要重新核验；原始字节摘要另存，未改原来源缓存。

交接包：`知识图谱/round14/condition_test_v2_annotation_packet/`，仓库副本 `evaluation/condition_test_v2/claude_annotation_packet/`。包内只有陈述、空标注表、通用 schema/词表、来源与歧义说明，没有算法输出、检索结果、分数或 gold。当前为 ready_for_Claude，尚未通过 Claude 工具传送或标注；待用户另行交回标注后冻结并评测。

交接清单 `HANDOFF_MANIFEST.json` SHA-256：`caf821b66b1e841c595822ca94362fc7a025f969365168eb9c8803000a7239b0`。冻结类型为 source_cards_only，标准答案尚未冻结。

小模型计量以共享 ledger 去重：**10/150 次 HTTP 请求，9 次逻辑抽取，9 次成功响应，1 次 429 重试**；已知输入 token 51,525、输出 12,705，总计 64,230；429 的 usage 未知，未按 0 计。无 length 截断。区域实验、来源审查和规范化评测调用均为 0。

没有输出密钥，没有部署或重启已有服务，没有处理 IXI 117 例保留组或 102311/105216，也没有释放新猕猴被试。新增运行只使用隔离开发检出；模板目录只读。
