# full_v2 全部错误与原始样本诊断

按模板、执行判定、逐条规范键任一不一致列出；只读既有响应，没有新调用或参数调整。

主要原因计数：{"provider_environment": 8, "template_mismatch": 9, "template_mismatch_with_margin_boundary": 4, "parameter_key_mismatch": 3, "split_or_insufficient_votes": 3, "no_type_valid_answer": 3}

## 1 · cat_morphometry · provider_environment

T1-weighted MRI scans, single scans, longitudinal series or BIDS datasets

原文引用：T1-weighted MRI
Single scans, longitudinal series or BIDS datasets

标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}} | {"slot": "T1", "type": "type:Volume.T1"} | [] |
| 2 | {"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}} | {"slot": "T1", "type": "type:Volume.T1"} | [] |
| 3 | {"template": "advisory", "parameters": {"text": "T1-weighted MRI scans, single scans, longitudinal series or BIDS datasets"}} | null | [] |
| 4 | {"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}} | {"slot": "T1", "type": "type:Volume.T1"} | [] |

## 2 · cat_morphometry · provider_environment

For MATLAB users, SPM12 or newer and MATLAB R2020a or newer are required; no additional MATLAB toolboxes are needed.

原文引用：SPM12 or newer
MATLAB R2020a or newer (Windows: R2022a, Apple Silicon: R2023b)
No additional MATLAB toolboxes

标准：{"template": "software", "parameters": {"commands": ["matlab", "spm12"]}}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "software", "parameters": {"commands": ["SPM12 or newer", "MATLAB R2020a or newer"]}} | {"commands": ["matlab", "spm12"]} | [] |
| 2 | {"template": "software", "parameters": {"commands": ["SPM12", "MATLAB R2020a", "MATLAB R2022a", "MATLAB R2023b"]}} | {"commands": ["matlab", "spm12"]} | [] |
| 3 | {"template": "software", "parameters": {"commands": ["SPM12", "MATLAB"]}} | {"commands": ["matlab", "spm12"]} | [] |

## 6 · cat_morphometry · provider_environment

The standalone version lacks some features such as parallelization and interactive help.

原文引用：Some features, such as parallelization and the interactive help, are not available.

标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |

## 7 · existing_curvature_sulc_profile · template_mismatch

Confirm that the surfaces have been smoothed and topology-corrected before using the morphometry values.

原文引用：Resmooth RH/LH white matter: smooths rh.orig and lh.orig surfaces

标准：{"template": "advisory", "parameters": null}

预测：{"decision": "accepted", "template": "provenance", "parameters": {"step": "recon-all"}}

原因：算法选择 provenance，审核版标准为 advisory。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
| 2 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
| 3 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
| 4 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
| 5 | {"template": "provenance", "parameters": {"step": "rescale"}} | {"step": "rescale"} | [] |

## 9 · fsl_vbm · template_mismatch

design.mat and design.con files specifying the cross-subject statistical model, with row order matching the image order from imglob.

原文引用：create your design.mat and design.con in your FSL-VBM directory; see the randomise manual

标准：{"template": "product_present", "parameters": {"slot": "design", "type": "type:StatsTable.DesignMatrix"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：算法选择 advisory，审核版标准为 product_present。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | "{\"template\": \"advisory\", \"parameters\": {}} \"parameters\": {}}" | null | ["unparseable or malformed parameter structure"] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | "{\"template\": \"advisory\", \"parameters\": {}}}}" | null | ["unparseable or malformed parameter structure"] |
| 5 | {"template": "advisory", "parameters": {}} | null | [] |

## 11 · fsl_vbm · provider_environment

All different populations included in the study must be represented in the template construction.

原文引用：All your different populations included in this study MUST be represented in the template construction.

标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |

## 14 · fsl_vbm · provider_environment

Check brain-extracted images (*_brain.*) in the struc directory after fslvbm_1_bet.

原文引用：CHECKING the brain images (*_brain.*) in your struc directory

标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | "{\"template\": \"advisory\", \"parameters\": {\"text\": \"CHECKING the brain images (*_brain.*) in your struc directory\"}} struc directory\"}}" | null | ["unparseable or malformed parameter structure"] |

## 15 · fsl_vbm · provider_environment

Check the template_GM_4D image in struc with the movie loop in fsleyes after template creation.

原文引用：CHECK the template_GM_4D image in struc with the movie loop in fsleyes.

标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |

## 16 · fsl_vbm · provider_environment

Check the 4D image of modulated registered GM images (GM_mod_merg) using the movie loop in fsleyes after fslvbm_3_proc.

原文引用：final CHECK of the 4D image of modulated registered GM images GM_mod_merg using the movie loop in fsleyes.

标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |

## 19 · global_surface_folding · provider_environment

White matter surface mesh of the cortical ribbon.

原文引用：our proposed method requires the bounding pial and white matter surfaces of the cortical ribbon as input

标准：{"template": "product_present", "parameters": {"slot": "white", "type": "type:Surface.White"}}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|

## 20 · global_surface_folding · template_mismatch

Point coordinates for convex hull computation.

原文引用：Coordinates of points to construct a convex hull from

标准：{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：算法选择 advisory，审核版标准为 product_present。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | {"template": "advisory", "parameters": {}} | null | [] |
| 5 | {"template": "advisory", "parameters": {}} | null | [] |

## 21 · global_surface_folding · template_mismatch

Cortical thickness estimate (average) for scaling law.

原文引用：we only had numerical values for the total and exposed surface area, as well a average cortical thickness estimates

标准：{"template": "product_present", "parameters": {"slot": "thickness", "type": "type:SurfaceMetric.Thickness"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：算法选择 advisory，审核版标准为 product_present。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | {"template": "product_present", "parameters": {"slot": "thickness", "type": "type:SurfaceMetric.Thickness"}} | {"slot": "thickness", "type": "type:SurfaceMetric.Thickness"} | [] |
| 4 | {"template": "advisory", "parameters": {}} | null | [] |
| 5 | {"template": "advisory", "parameters": {}} | null | [] |

## 33 · hcp_structural_pipeline · template_mismatch

T1/T2 structural images are processed by the three structural batch scripts.

原文引用：处理T1/T2结构像

标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：算法选择 advisory，审核版标准为 product_present。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | {"template": "advisory", "parameters": {}} | null | [] |
| 5 | {"template": "advisory", "parameters": {}} | null | [] |

## 36 · local_gyrification · template_mismatch_with_margin_boundary

The pial surface file (?h.pial) for the subject, produced by the recon-all -all stream.

原文引用：usage of the -localGI feature assumes that a subject has already been processed by the freesurfer {{{recon-all -s <subjid> -all}}} stream, such that the ?h.pial surface files exist

标准：{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}

预测：{"decision": "review", "template": "provenance", "parameters": {"step": "recon-all"}}

原因：3/5 对 2/5 的票差在浮点计算中得到略小于 0.2 的值，触发 bundle 原有的 margin 阈值；本轮未改算法。主模板若与标准不同，即使修复数值边界，该模板分歧也仍然存在。；support=0.6, margin=0.19999999999999996, votes={"provenance:{\"step\": \"recon-all\"}": 3, "product_present:{\"slot\": \"pial\", \"type\": \"type:Surface.Pial\"}": 2}；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}} | {"slot": "pial", "type": "type:Surface.Pial"} | [] |
| 2 | {"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}} | {"slot": "pial", "type": "type:Surface.Pial"} | [] |
| 3 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
| 4 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
| 5 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |

## 38 · local_gyrification · parameter_key_mismatch

MATLAB with Image Processing Toolbox and $FREESURFER_HOME/matlab in the MATLAB path.

原文引用：MATLAB is required to use the -localGI feature. Also, you will need their Image Processing Toolbox.

标准：{"template": "software", "parameters": {"commands": ["matlab"]}}

预测：{"decision": "accepted", "template": "software", "parameters": {"commands": ["image", "matlab"]}}

原因：严格规范键差异：{"commands": {"gold": ["matlab"], "prediction": ["image", "matlab"]}}

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |
| 2 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |
| 3 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |
| 4 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |
| 5 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |

## 40 · local_gyrification · parameter_key_mismatch

MATLAB and its Image Processing Toolbox must be installed and accessible.

原文引用：MATLAB is required to use the -localGI feature. Also, you will need their Image Processing Toolbox.

标准：{"template": "software", "parameters": {"commands": ["matlab"]}}

预测：{"decision": "accepted", "template": "software", "parameters": {"commands": ["image", "matlab"]}}

原因：严格规范键差异：{"commands": {"gold": ["matlab"], "prediction": ["image", "matlab"]}}；软件名按 bundle 的首个字母数字 token 归一化；含下划线或连字符的命令可能被截短，原始与归一化参数均保留。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |
| 2 | {"template": "software", "parameters": {"commands": ["matlab", "image_processing_toolbox"]}} | {"commands": ["image", "matlab"]} | [] |
| 3 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |
| 4 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |
| 5 | {"template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}} | {"commands": ["image", "matlab"]} | [] |

## 41 · local_gyrification · parameter_key_mismatch

The MATLAB path must include $FREESURFER_HOME/matlab, set up in ~/matlab/startup.m.

原文引用：You will also need $FREESURFER_HOME/matlab in your matlab path set up in your ~/matlab/starup.m script.

标准：{"template": "software", "parameters": {"commands": ["matlab"]}}

预测：{"decision": "accepted", "template": "software", "parameters": {"commands": ["freesurfer", "matlab"]}}

原因：严格规范键差异：{"commands": {"gold": ["matlab"], "prediction": ["freesurfer", "matlab"]}}；软件名按 bundle 的首个字母数字 token 归一化；含下划线或连字符的命令可能被截短，原始与归一化参数均保留。

此条标准按用户要求暂采 Claude 建议，仍待用户决定。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "software", "parameters": {"commands": ["matlab"]}} | {"commands": ["matlab"]} | [] |
| 2 | {"template": "software", "parameters": {"commands": ["matlab", "$FREESURFER_HOME/matlab"]}} | {"commands": ["freesurfer", "matlab"]} | [] |
| 3 | {"template": "software", "parameters": {"commands": ["matlab", "freesurfer matlab path"]}} | {"commands": ["freesurfer", "matlab"]} | [] |
| 4 | {"template": "software", "parameters": {"commands": ["matlab", "freesurfer"]}} | {"commands": ["freesurfer", "matlab"]} | [] |
| 5 | {"template": "software", "parameters": {"commands": ["matlab", "freesurfer"]}} | {"commands": ["freesurfer", "matlab"]} | [] |

## 47 · macaque_civet · split_or_insufficient_votes

The pipeline is designed for macaque brains and uses a length scale of 0.4 relative to human brain size.

原文引用：A length scale of 0.4 was derived from the cubic root of the macaque-to-human volume ratio

标准：{"template": "attr_in", "parameters": {"slot": "T1", "attr": "species", "values": ["macaque"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：有效规范键的票数或票差不足，算法将最佳提案送审。；support=0.4, margin=0.0, votes={"advisory": 2, "scale_check:{\"metric\": \"length scale (macaque-to-human volume ratio)\"}": 2}；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | "{\"template\": \"advisory\", \"parameters\": {}} {}}" | null | ["unparseable or malformed parameter structure"] |
| 4 | {"template": "scale_check", "parameters": {"metric": "length scale (macaque-to-human volume ratio)"}} | {"metric": "length scale (macaque-to-human volume ratio)"} | [] |
| 5 | {"template": "scale_check", "parameters": {"metric": "length scale (macaque-to-human volume ratio)"}} | {"metric": "length scale (macaque-to-human volume ratio)"} | [] |

## 53 · macaque_civet · template_mismatch

The pipeline is not validated for species other than macaques; adaptations for other primates would require appropriate length scales and templates.

原文引用：Further adaptations of the pipeline to other non-human primate brains should be straightforward by introducing the appropriate length scales and supplying species specific templates.

标准：{"template": "attr_in", "parameters": {"slot": "T1", "attr": "species", "values": ["macaque"]}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：算法选择 advisory，审核版标准为 attr_in。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | "{\"template\": \"advisory\", \"parameters\": {}} \"parameters\": {}}" | null | ["unparseable or malformed parameter structure"] |
| 4 | {"template": "advisory", "parameters": {}} | null | [] |
| 5 | {"template": "advisory", "parameters": {}} | null | [] |

## 56 · nhp_macapype · template_mismatch

Input data must be in BIDS format, with T1w and T2w images expected.

原文引用：All the data have to be in BIDS format to run properly

标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：算法选择 advisory，审核版标准为 product_present。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | {"template": "attr_in", "parameters": {"slot": "T1", "attr": "space", "values": ["BIDS"]}} | {"slot": "T1", "attr": "space", "values": ["BIDS"]} | ["values outside the space domain"] |
| 5 | {"template": "advisory", "parameters": {}} | null | [] |

## 57 · nhp_macapype · template_mismatch

T1 weighted images are expected with the _T1w BIDS extension.

原文引用：_T1w (BIDS) extension is expected for T1 weighted images

标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：算法选择 advisory，审核版标准为 product_present。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "advisory"} | null | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | {"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}} | {"slot": "T1", "type": "type:Volume.T1"} | [] |
| 5 | {"template": "advisory", "parameters": {}} | null | [] |

## 71 · samseg_segmentation · no_type_valid_answer

All input volumes must be co-registered with each other and have the same image grid size and voxel dimensions.

原文引用：the only requirement is that all input volumes are co-registered with each other, and have the same image grid size and voxel dimensions

标准：{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：样本没有形成可用的类型合法答案；逐样本问题见下表。；support=None, margin=None, votes={}；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 2 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 3 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 4 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 5 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |

## 73 · samseg_segmentation · split_or_insufficient_votes

For longitudinal processing, all time points must be co-registered and reformatted to the same image grid, using an unbiased reference template.

原文引用：longitudinal SAMSEG expects all its input images to have been co-registered and reformatted to the same image grid beforehand

标准：{"template": "attr_equal", "parameters": {"slots": ["T1", "timepoints"], "attrs": ["space", "voxel_size"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：有效规范键的票数或票差不足，算法将最佳提案送审。；support=0.2, margin=0.2, votes={"advisory": 1}；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "attr_equal", "parameters": {"slots": ["timepoints"], "attrs": ["space", "voxel_size"]}} | {"slots": ["timepoints"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 2 | {"template": "attr_equal", "parameters": {"slots": ["timepoints"], "attrs": ["space", "voxel_size"]}} | {"slots": ["timepoints"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 3 | {"template": "attr_equal", "parameters": {"slots": ["timepoints"], "attrs": ["space", "voxel_size"]}} | {"slots": ["timepoints"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 4 | {"template": "advisory", "parameters": {}} | null | [] |
| 5 | {"template": "attr_equal", "parameters": {"slots": ["timepoints"], "attrs": ["space", "voxel_size"]}} | {"slots": ["timepoints"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |

## 75 · samseg_segmentation · no_type_valid_answer

For multi-contrast input, all volumes must be co-registered and have the same image grid size and voxel dimensions.

原文引用：all input volumes are co-registered with each other, and have the same image grid size and voxel dimensions

标准：{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：样本没有形成可用的类型合法答案；逐样本问题见下表。；support=None, margin=None, votes={}；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 2 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 3 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 4 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 5 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |

## 78 · samseg_segmentation · no_type_valid_answer

Verify that all input volumes are co-registered and have the same image grid size and voxel dimensions.

原文引用：the only requirement is that all input volumes are co-registered with each other, and have the same image grid size and voxel dimensions

标准：{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：样本没有形成可用的类型合法答案；逐样本问题见下表。；support=None, margin=None, votes={}；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 2 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 3 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 4 | {"template": "attr_equal", "parameters": {"slots": ["volumes"], "attrs": ["space", "voxel_size"]}} | {"slots": ["volumes"], "attrs": ["space", "voxel_size"]} | ["slots must list at least two known slots"] |
| 5 | "{\"template\": \"attr_equal\", \"parameters\": {\"slots\": [\"volumes\"], \"attrs\": [\"space\", \"voxel_size\"]}}el_size\"]}}" | null | ["unparseable or malformed parameter structure"] |

## 82 · samseg_segmentation · template_mismatch_with_margin_boundary

The first time the MS lesion module is run, the user may be prompted to install Tensorflow.

原文引用：The first time you run this module, you may be prompted to install Tensorflow

标准：{"template": "advisory", "parameters": null}

预测：{"decision": "review", "template": "software", "parameters": {"commands": ["tensorflow"]}}

原因：3/5 对 2/5 的票差在浮点计算中得到略小于 0.2 的值，触发 bundle 原有的 margin 阈值；本轮未改算法。主模板若与标准不同，即使修复数值边界，该模板分歧也仍然存在。；support=0.6, margin=0.19999999999999996, votes={"software:{\"commands\": [\"tensorflow\"]}": 3, "advisory": 2}

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "software", "parameters": {"commands": ["Tensorflow"]}} | {"commands": ["tensorflow"]} | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | {"template": "software", "parameters": {"commands": ["Tensorflow"]}} | {"commands": ["tensorflow"]} | [] |
| 4 | {"template": "advisory", "parameters": {}} | null | [] |
| 5 | {"template": "software", "parameters": {"commands": ["Tensorflow"]}} | {"commands": ["tensorflow"]} | [] |

## 86 · surface_annotation_roi · template_mismatch

Verify that the number of morphometry values matches the number of vertices in the annotation.

原文引用：labelsndarray, shape (n_vertices,)

标准：{"template": "attr_equal", "parameters": {"slots": ["annotation", "metric"], "attrs": ["mesh"]}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：算法选择 advisory，审核版标准为 attr_equal。；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory", "parameters": {}} | null | [] |
| 2 | {"template": "attr_equal", "parameters": {"slots": ["metric", "annotation"], "attrs": ["mesh"]}} | {"slots": ["metric", "annotation"], "attrs": ["mesh"]} | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | {"template": "advisory", "parameters": {}} | null | [] |
| 5 | "{\"template\": \"advisory\", \"parameters\": {}}\": {}}" | null | ["unparseable or malformed parameter structure"] |

## 95 · surface_mesh_area · template_mismatch_with_margin_boundary

Verify that the mesh is in triangular format as expected by read_geometry.

原文引用：Read a triangular format Freesurfer surface mesh.

标准：{"template": "advisory", "parameters": null}

预测：{"decision": "review", "template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["triangular"]}}

原因：3/5 对 2/5 的票差在浮点计算中得到略小于 0.2 的值，触发 bundle 原有的 margin 阈值；本轮未改算法。主模板若与标准不同，即使修复数值边界，该模板分歧也仍然存在。；support=0.6, margin=0.19999999999999996, votes={"attr_in:{\"attr\": \"mesh\", \"slot\": \"surface\", \"values\": [\"triangular\"]}": 3, "advisory": 2}

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["triangular"]}} | {"slot": "surface", "attr": "mesh", "values": ["triangular"]} | [] |
| 2 | {"template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["triangular"]}} | {"slot": "surface", "attr": "mesh", "values": ["triangular"]} | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | {"template": "advisory", "parameters": {}} | null | [] |
| 5 | {"template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["triangular"]}} | {"slot": "surface", "attr": "mesh", "values": ["triangular"]} | [] |

## 99 · surface_reconstruction_qc · split_or_insufficient_votes

T1-weighted anatomical image(s) in DICOM or other native scanner format.

原文引用：the raw data from the scan must be converted into a format recognized by FreeSurfer

标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：有效规范键的票数或票差不足，算法将最佳提案送审。；support=0.4, margin=0.0, votes={"advisory": 2, "product_present:{\"slot\": \"T1\", \"type\": \"type:Volume.T1\"}": 2}；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "advisory"} | null | [] |
| 2 | "{\"template\": \"product_present\", \"parameters\": {\"slot\": \"T1\", \"type\": \"type:Volume.T1\"}}1\"}}" | null | ["unparseable or malformed parameter structure"] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | {"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}} | {"slot": "T1", "type": "type:Volume.T1"} | [] |
| 5 | {"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}} | {"slot": "T1", "type": "type:Volume.T1"} | [] |

## 101 · surface_reconstruction_qc · template_mismatch_with_margin_boundary

Output volumes from recon-all processing, including T1.mgz, brainmask.mgz, and surface files.

原文引用：load the T1 and brainmask images as underlays in freeview, and overlay the white and pial surfaces

标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "review", "template": "provenance", "parameters": {"step": "recon-all"}}

原因：3/5 对 2/5 的票差在浮点计算中得到略小于 0.2 的值，触发 bundle 原有的 margin 阈值；本轮未改算法。主模板若与标准不同，即使修复数值边界，该模板分歧也仍然存在。；support=0.6, margin=0.19999999999999996, votes={"provenance:{\"step\": \"recon-all\"}": 3, "advisory": 2}；执行判定不一致；review 按未接受计分。

| 样本 | 原始答案 | 归一化参数 | 类型问题 |
|---|---|---|---|
| 1 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
| 2 | {"template": "advisory", "parameters": {}} | null | [] |
| 3 | {"template": "advisory", "parameters": {}} | null | [] |
| 4 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
| 5 | {"template": "provenance", "parameters": {"step": "recon-all"}} | {"step": "recon-all"} | [] |
