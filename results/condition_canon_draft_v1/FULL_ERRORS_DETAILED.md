# Full 组逐条错误与调用诊断

以下标准答案均为未审核草稿。任何模板、可执行判定或逐条规范键不一致均列入；接口失败另列类别。

## 1 · cat_morphometry

T1-weighted MRI scans, single scans, longitudinal series or BIDS datasets

草稿标准：`{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}`

预测：`{"decision": "accepted", "template": "cardinality", "parameters": {"object": "T1", "minimum": 1}}`

原因：模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；规范键参数与草稿标准不一致（未对同义表示额外修正）

## 2 · cat_morphometry

For MATLAB users, SPM12 or newer and MATLAB R2020a or newer are required; no additional MATLAB toolboxes are needed.

草稿标准：`{"template": "software", "parameters": {"commands": ["matlab", "spm12"]}}`

预测：`{"decision": "accepted", "template": "software", "parameters": {"commands": ["SPM12 or newer", "MATLAB R2020a or newer (Windows: R2022a, Apple Silicon: R2023b)", "No additional MATLAB toolboxes"]}}`

原因：规范键参数与草稿标准不一致（未对同义表示额外修正）；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 5 · cat_morphometry

A sample homogeneity check flags outliers before statistics.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "Sample homogeneity check flags outliers before statistics"}}`

原因：待审核：score=0.3272, margin=0.3272, support=0.40；模板标签与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 6 · cat_morphometry

The standalone version lacks some features such as parallelization and interactive help.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "software", "parameters": {"commands": ["parallelization", "interactive help"]}}`

原因：待审核：score=0.2374, margin=0.2374, support=0.20；模板标签与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 7 · existing_curvature_sulc_profile

Confirm that the surfaces have been smoothed and topology-corrected before using the morphometry values.

草稿标准：`{"template": "provenance", "parameters": {"step": "topology correction"}}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "Resmooth RH/LH white matter: smooths rh.orig and lh.orig surfaces"}}`

原因：待审核：score=0.1993, margin=0.0113, support=0.20；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 8 · fsl_vbm

A template_list file containing the names of selected T1 images to be used for template construction, with equal numbers from each group.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "T1", "type": "template_list"}}`

原因：待审核：score=0.3139, margin=0.3139, support=0.40；模板标签与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 9 · fsl_vbm

design.mat and design.con files specifying the cross-subject statistical model, with row order matching the image order from imglob.

草稿标准：`{"template": "product_present", "parameters": {"slot": "design", "type": "type:StatsTable.DesignMatrix"}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 10 · fsl_vbm

A GM mask (GM_mask) and the 4D multi-subject concatenated processed data (e.g., GM_mod_merg_s3) for running randomise.

草稿标准：`{"template": "product_present", "parameters": {"slot": "mask", "type": "type:Volume.BrainMask"}}`

预测：`{"decision": "review", "template": "attr_equal", "parameters": {"slots": ["mask", "volumes"], "attrs": ["subject", "species", "space", "voxel_size", "scale_status"]}}`

原因：待审核：score=0.1906, margin=0.1906, support=0.20；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 13 · fsl_vbm

The order of rows in design.mat must match the order of images when doing imglob * in the FSL-VBM directory.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "provider_error", "template": null, "parameters": null}`

原因：接口/预算失败，单列为环境失败而非语义错误：Maximum attempts for this logical call were already consumed；模板标签与草稿标准不一致

## 14 · fsl_vbm

Check brain-extracted images (*_brain.*) in the struc directory after fslvbm_1_bet.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "brain-extracted images (*_brain.*) in struc directory after fslvbm_1_bet"}}`

原因：待审核：score=0.1539, margin=0.0000, support=0.20；模板标签与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 15 · fsl_vbm

Check the template_GM_4D image in struc with the movie loop in fsleyes after template creation.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "CHECK the template_GM_4D image in struc with the movie loop in fsleyes."}}`

原因：待审核：score=0.3087, margin=0.1400, support=0.40；模板标签与草稿标准不一致

## 16 · fsl_vbm

Check the 4D image of modulated registered GM images (GM_mod_merg) using the movie loop in fsleyes after fslvbm_3_proc.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "GM_mod_merg"}}`

原因：待审核：score=0.4517, margin=0.2800, support=0.60；模板标签与草稿标准不一致

## 17 · fsl_vbm

FSL-VBM v1.1 analysis is not compatible with an older analysis due to the switch from IRTK to FNIRT.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "FSL-VBM v1.1 analysis is not compatible with an older analysis due to the switch from IRTK to FNIRT."}}`

原因：待审核：score=0.1953, margin=0.0000, support=0.20；模板标签与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 18 · global_surface_folding

Pial surface mesh of the cortical ribbon.

草稿标准：`{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "pial", "type": "mesh"}}`

原因：待审核：score=0.1896, margin=0.1896, support=0.20；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 19 · global_surface_folding

White matter surface mesh of the cortical ribbon.

草稿标准：`{"template": "product_present", "parameters": {"slot": "white", "type": "type:Surface.White"}}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "white", "type": "mesh"}}`

原因：待审核：score=0.3296, margin=0.3296, support=0.40；可执行/非可执行判定与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 20 · global_surface_folding

Point coordinates for convex hull computation.

草稿标准：`{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 21 · global_surface_folding

Cortical thickness estimate (average) for scaling law.

草稿标准：`{"template": "product_present", "parameters": {"slot": "thickness", "type": "type:SurfaceMetric.Thickness"}}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "thickness"}}`

原因：待审核：score=0.2636, margin=0.0000, support=0.20；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 23 · global_surface_folding

Coarse-graining erases morphological features smaller than the specified scale while preserving surface integrity.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "scale_check", "parameters": {"metric": "voxel_size"}}`

原因：待审核：score=0.2468, margin=0.2468, support=0.20；模板标签与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 24 · global_surface_folding

Isometric rescaling is applied to leave dimensionless shape properties unaffected.

草稿标准：`{"template": "scale_check", "parameters": {"metric": "shape"}}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "we apply an isometric rescaling process that leaves all dimensionless shape properties unaffected"}}`

原因：待审核：score=0.4981, margin=0.1400, support=0.60；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致

## 25 · global_surface_folding

Quality check reconstructed surfaces by visual inspection.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "visual inspection"}}`

原因：待审核：score=0.3781, margin=0.1400, support=0.40；模板标签与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 26 · global_surface_folding

Verify that coarse-grained cortices follow the scaling law with high R².

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "attr_in", "parameters": {"slot": "surface", "attr": "scale_status", "values": ["coarse-grained"]}}`

原因：待审核：score=0.1853, margin=0.0000, support=0.20；模板标签与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 27 · global_surface_folding

Check that K remains near-invariant across scales and species.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "variance in K across scales and all 11 species <0.01"}}`

原因：待审核：score=0.3044, margin=0.0000, support=0.40；模板标签与草稿标准不一致

## 29 · global_surface_folding

Coarse-grained brain surfaces are algorithmic outputs and not to be directly likened to actual brain surfaces in terms of fold location or shape.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "attr_in", "parameters": {"slot": "surface", "attr": "scale_status", "values": ["coarse-grained"]}}`

原因：待审核：score=0.2419, margin=0.2419, support=0.20；模板标签与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 30 · global_surface_folding

The model cannot capture large-scale features such as the longitudinal fissure, sylvian fissure, and specific gyri and sulci.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "scale_check", "parameters": {"metric": "large-scale features"}}`

原因：待审核：score=0.3819, margin=0.1400, support=0.40；模板标签与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 33 · hcp_structural_pipeline

T1/T2 structural images are processed by the three structural batch scripts.

草稿标准：`{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "处理T1/T2结构像"}}`

原因：待审核：score=0.3471, margin=0.1400, support=0.40；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 36 · local_gyrification

The pial surface file (?h.pial) for the subject, produced by the recon-all -all stream.

草稿标准：`{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "pial", "type": "surface"}}`

原因：待审核：score=0.2005, margin=0.2005, support=0.20；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 37 · local_gyrification

The subject's surf directory containing the pial surface files.

草稿标准：`{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "pial", "type": "surface"}}`

原因：待审核：score=0.3326, margin=0.1400, support=0.40；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 38 · local_gyrification

MATLAB with Image Processing Toolbox and $FREESURFER_HOME/matlab in the MATLAB path.

草稿标准：`{"template": "software", "parameters": {"commands": ["matlab"]}}`

预测：`{"decision": "review", "template": "software", "parameters": {"commands": ["matlab -nodisplay -nosplash -r \"addpath(fullfile(getenv('FREESURFER_HOME'),'matlab')); assert(~isempty(ver('images'))); exit\""]}}`

原因：待审核：score=0.2698, margin=0.0000, support=0.20；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 39 · local_gyrification

The subject must have been processed with the full recon-all stream before using -localGI.

草稿标准：`{"template": "provenance", "parameters": {"step": "recon-all"}}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "recon-all -s <subjid> -all"}}`

原因：待审核：score=0.4328, margin=0.0000, support=0.40；可执行/非可执行判定与草稿标准不一致

## 40 · local_gyrification

MATLAB and its Image Processing Toolbox must be installed and accessible.

草稿标准：`{"template": "software", "parameters": {"commands": ["matlab"]}}`

预测：`{"decision": "review", "template": "software", "parameters": {"commands": ["MATLAB", "Image Processing Toolbox"]}}`

原因：待审核：score=0.4066, margin=0.1400, support=0.40；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 41 · local_gyrification

The MATLAB path must include $FREESURFER_HOME/matlab, set up in ~/matlab/startup.m.

草稿标准：`{"template": "software", "parameters": {"commands": ["matlab"]}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样；类型检查问题：commands must be a non-empty list

## 42 · local_gyrification

Check for topological defects of the pial surface using mris_euler_number, as defects cause mris_compute_lgi to crash.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "attr_in", "parameters": {"slot": "pial", "attr": "mesh", "values": ["defective"]}}`

原因：待审核：score=0.2186, margin=0.2186, support=0.20；模板标签与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 44 · macaque_civet

T1-weighted MR scan of a macaque brain as the primary input.

草稿标准：`{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}`

预测：`{"decision": "accepted", "template": "attr_in", "parameters": {"slot": "T1", "attr": "species", "values": ["macaque"]}}`

原因：模板标签与草稿标准不一致；规范键参数与草稿标准不一致（未对同义表示额外修正）；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 46 · macaque_civet

NMT brain mask and tissue priors for registration and classification.

草稿标准：`{"template": "product_present", "parameters": {"slot": "mask", "type": "type:Volume.BrainMask"}}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "Registration, using minctracc, proceeds by specifying the brain mask on the target image only, herein the NMT volume with its associated brain mask"}}`

原因：待审核：score=0.3038, margin=0.1400, support=0.40；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 47 · macaque_civet

The pipeline is designed for macaque brains and uses a length scale of 0.4 relative to human brain size.

草稿标准：`{"template": "attr_in", "parameters": {"slot": "T1", "attr": "species", "values": ["macaque"]}}`

预测：`{"decision": "review", "template": "scale_check", "parameters": {"metric": "0.4"}}`

原因：待审核：score=0.2550, margin=0.0000, support=0.20；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 48 · macaque_civet

Processing is performed in the NMT standardized space.

草稿标准：`{"template": "attr_in", "parameters": {"slot": "T1", "attr": "space", "values": ["NMT_v2"]}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样；类型检查问题：values outside the space domain

## 49 · macaque_civet

The pipeline requires T1w scans; T2-weighted or proton density scans are optional for multimodal classification.

草稿标准：`{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}`

预测：`{"decision": "accepted", "template": "cardinality", "parameters": {"object": "T1", "minimum": 1}}`

原因：模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；规范键参数与草稿标准不一致（未对同义表示额外修正）；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 51 · macaque_civet

Quality control includes visual inspection of brain masks and surfaces for accuracy.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "accuracy"}}`

原因：待审核：score=0.5875, margin=0.4200, support=0.80；模板标签与草稿标准不一致

## 53 · macaque_civet

The pipeline is not validated for species other than macaques; adaptations for other primates would require appropriate length scales and templates.

草稿标准：`{"template": "attr_in", "parameters": {"slot": "T1", "attr": "species", "values": ["macaque"]}}`

预测：`{"decision": "review", "template": "attr_in", "parameters": {"slot": "T1", "attr": "species", "values": ["macaque"]}}`

原因：待审核：score=0.2175, margin=0.0298, support=0.20；可执行/非可执行判定与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 55 · macaque_civet

The pipeline may require manual intervention for custom brain masks in rare registration failures.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "accepted", "template": "attr_in", "parameters": {"slot": "mask", "attr": "space", "values": ["native"]}}`

原因：模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致

## 56 · nhp_macapype

Input data must be in BIDS format, with T1w and T2w images expected.

草稿标准：`{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 57 · nhp_macapype

T1 weighted images are expected with the _T1w BIDS extension.

草稿标准：`{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "_T1w"}}`

原因：待审核：score=0.3568, margin=0.1400, support=0.40；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 58 · nhp_macapype

T2 weighted images are expected with the _T2w BIDS extension.

草稿标准：`{"template": "product_present", "parameters": {"slot": "T2", "type": "type:Volume.T1"}}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "_T2w (BIDS) extension is expected for T2 weighted images"}}`

原因：待审核：score=0.3568, margin=0.3568, support=0.40；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 62 · nhp_macapype

The -soft parameter must be either SPM or ANTS, with SPM requiring a specific version of macapype/skullTo3d not available by default.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "software", "parameters": {"commands": ["SPM", "ANTS"]}}`

原因：待审核：score=0.4999, margin=0.4999, support=0.60；模板标签与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 67 · nhp_macapype

The _4animal option uses bet4animal (FSL) for brain extraction, for faster computation; by default atlas_brex is used.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "software", "parameters": {"commands": ["bet4animal", "atlas_brex"]}}`

原因：待审核：score=0.1923, margin=0.1923, support=0.20；模板标签与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样；类型检查问题：commands must be a non-empty list

## 69 · nhp_macapype

Some templates are available in downgraded versions (e.g., baboon1_0p6, macaque_0p5) showing significant decrease in processing time with low reduction in quality, but not all combinations are available.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "NB: some templates are available in downgraded versions: baboon1_0p6, baboon2_0p6, baboon3_0p6 and macaque_0p5, and show significant decrease in processing time with low reduction in quality. However, not all combinations are available"}}`

原因：待审核：score=0.1804, margin=0.1804, support=0.20；模板标签与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 70 · samseg_segmentation

One or more co-registered MRI volumes in Nifti (.nii/.nii.gz) or FreeSurfer (.mgz) format.

草稿标准：`{"template": "product_present", "parameters": {"slot": "volumes", "type": "type:Volume"}}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "volumes", "type": "MRI"}}`

原因：待审核：score=0.1632, margin=0.1632, support=0.20；可执行/非可执行判定与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 71 · samseg_segmentation

All input volumes must be co-registered with each other and have the same image grid size and voxel dimensions.

草稿标准：`{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 73 · samseg_segmentation

For longitudinal processing, all time points must be co-registered and reformatted to the same image grid, using an unbiased reference template.

草稿标准：`{"template": "attr_equal", "parameters": {"slots": ["T1", "timepoints"], "attrs": ["space", "voxel_size"]}}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "co-registered and reformatted to the same image grid using an unbiased reference template"}}`

原因：待审核：score=0.4667, margin=0.4667, support=0.60；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 74 · samseg_segmentation

Preprocessing with FreeSurfer is neither required nor recommended for basic SAMSEG.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "Preprocessing of the scan(s) with FreeSurfer is neither required nor recommended"}}`

原因：待审核：score=0.3252, margin=0.3252, support=0.40；模板标签与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 75 · samseg_segmentation

For multi-contrast input, all volumes must be co-registered and have the same image grid size and voxel dimensions.

草稿标准：`{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；5/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 78 · samseg_segmentation

Verify that all input volumes are co-registered and have the same image grid size and voxel dimensions.

草稿标准：`{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样；类型检查问题：values must be a non-empty list

## 82 · samseg_segmentation

The first time the MS lesion module is run, the user may be prompted to install Tensorflow.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "provenance", "parameters": {"step": "The first time you run this module, you may be prompted to install Tensorflow"}}`

原因：待审核：score=0.1872, margin=0.1872, support=0.20；模板标签与草稿标准不一致

## 84 · surface_annotation_roi

Optionally a FreeSurfer .label file giving vertex indices, with optional per-vertex scalars.

草稿标准：`{"template": "product_present", "parameters": {"slot": "label", "type": "type:Label"}}`

预测：`{"decision": "review", "template": "software", "parameters": {"commands": ["Load in a Freesurfer .label file."]}}`

原因：待审核：score=0.1796, margin=0.1796, support=0.20；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样；类型检查问题：exclude must be a non-empty list

## 85 · surface_annotation_roi

Optionally a triangular surface mesh geometry file supplying vertex coordinates and faces.

草稿标准：`{"template": "product_present", "parameters": {"slot": "surface", "type": "type:Surface"}}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "surface", "type": "mesh"}}`

原因：待审核：score=0.4794, margin=0.4794, support=0.60；可执行/非可执行判定与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 86 · surface_annotation_roi

Verify that the number of morphometry values matches the number of vertices in the annotation.

草稿标准：`{"template": "attr_equal", "parameters": {"slots": ["annotation", "metric"], "attrs": ["mesh"]}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 88 · surface_mesh_area

A FreeSurfer surface mesh file in triangular format, e.g., white or pial surface.

草稿标准：`{"template": "product_present", "parameters": {"slot": "surface", "type": "type:Surface"}}`

预测：`{"decision": "review", "template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["triangular"]}}`

原因：待审核：score=0.4767, margin=0.4767, support=0.60；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 89 · surface_mesh_area

Vertex coordinates array (nvtx x 3) from the surface mesh.

草稿标准：`{"template": "product_present", "parameters": {"slot": "surface", "type": "type:Surface"}}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "surface", "type": "vertex_coordinates"}}`

原因：待审核：score=0.1779, margin=0.0000, support=0.20；可执行/非可执行判定与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 90 · surface_mesh_area

Face array (nfaces x 3) defining mesh triangles.

草稿标准：`{"template": "product_present", "parameters": {"slot": "surface", "type": "type:Surface"}}`

预测：`{"decision": "review", "template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["nfaces x 3 array of defining mesh triangles"]}}`

原因：待审核：score=0.1704, margin=0.1704, support=0.20；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 91 · surface_mesh_area

Triangle vertices in (n, 3, 3) float form for area computation.

草稿标准：`{"template": "product_present", "parameters": {"slot": "surface", "type": "type:Surface"}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；草稿标准模板不在检索 top-3 中；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样；类型检查问题：values must be a non-empty list

## 92 · surface_mesh_area

The mesh must be in triangular format as read by nibabel's read_geometry.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["triangular"]}}`

原因：待审核：score=0.5254, margin=0.5254, support=0.60；模板标签与草稿标准不一致；2/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 94 · surface_mesh_area

The area function computes the sum area of input triangles.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "product_present", "parameters": {"slot": "surface", "type": "mesh"}}`

原因：待审核：score=0.1718, margin=0.1718, support=0.20；模板标签与草稿标准不一致；3/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 95 · surface_mesh_area

Verify that the mesh is in triangular format as expected by read_geometry.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "accepted", "template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["triangular"]}}`

原因：模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致

## 99 · surface_reconstruction_qc

T1-weighted anatomical image(s) in DICOM or other native scanner format.

草稿标准：`{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；4/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 100 · surface_reconstruction_qc

Subject directory created via recon-all -i command.

草稿标准：`{"template": "provenance", "parameters": {"step": "recon-all"}}`

预测：`{"decision": "review", "template": "software", "parameters": {"commands": ["recon-all -i <path-to-first-structural> [-i <path-to-second-structural>] -s <subjid>"]}}`

原因：待审核：score=0.4793, margin=0.4793, support=0.60；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；1/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样；类型检查问题：commands must be a non-empty list

## 101 · surface_reconstruction_qc

Output volumes from recon-all processing, including T1.mgz, brainmask.mgz, and surface files.

草稿标准：`{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}`

预测：`{"decision": "advisory", "template": "advisory", "parameters": null}`

原因：没有通过类型检查的模板/参数；none 或无法解析输出也计入此分支；模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致；5/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样

## 102 · surface_reconstruction_qc

Anatomical data should have good quality: strong contrast between tissue types, no movement, high resolution.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "review", "template": "plausibility", "parameters": {"metric": "anatomical data quality: strong contrast between tissue types, no movement, high resolution"}}`

原因：待审核：score=0.4617, margin=0.1400, support=0.60；模板标签与草稿标准不一致

## 103 · surface_reconstruction_qc

Soft failures occur when recon-all finishes without errors but output has obvious errors needing fixes.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "provider_error", "template": null, "parameters": null}`

原因：接口/预算失败，单列为环境失败而非语义错误：Provider request failed (http_error, HTTP 429); see metered ledger；模板标签与草稿标准不一致

## 107 · surface_reconstruction_qc

Topological defects are very rare since FreeSurfer version 6.0 and are usually automatically fixed during recon-all.

草稿标准：`{"template": "advisory", "parameters": null}`

预测：`{"decision": "accepted", "template": "software", "parameters": {"commands": ["recon-all"]}}`

原因：模板标签与草稿标准不一致；可执行/非可执行判定与草稿标准不一致
