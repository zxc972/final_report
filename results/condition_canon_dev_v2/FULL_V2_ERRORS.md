# full_v2 开发集错误清单

逐条列出模板、执行判定或严格规范键不一致；不据此调参。

## 1 · cat_morphometry

T1-weighted MRI scans, single scans, longitudinal series or BIDS datasets

原文引用：T1-weighted MRI
Single scans, longitudinal series or BIDS datasets

审核版标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：运行/接口失败，单列环境或输出结构问题；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{}

## 2 · cat_morphometry

For MATLAB users, SPM12 or newer and MATLAB R2020a or newer are required; no additional MATLAB toolboxes are needed.

原文引用：SPM12 or newer
MATLAB R2020a or newer (Windows: R2022a, Apple Silicon: R2023b)
No additional MATLAB toolboxes

审核版标准：{"template": "software", "parameters": {"commands": ["matlab", "spm12"]}}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：运行/接口失败，单列环境或输出结构问题；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{}

## 6 · cat_morphometry

The standalone version lacks some features such as parallelization and interactive help.

原文引用：Some features, such as parallelization and the interactive help, are not available.

审核版标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：运行/接口失败，单列环境或输出结构问题；主模板与审核版开发集标准不一致

票数：{}

## 7 · existing_curvature_sulc_profile

Confirm that the surfaces have been smoothed and topology-corrected before using the morphometry values.

原文引用：Resmooth RH/LH white matter: smooths rh.orig and lh.orig surfaces

审核版标准：{"template": "advisory", "parameters": null}

预测：{"decision": "accepted", "template": "provenance", "parameters": {"step": "recon-all"}}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"provenance:{\"step\": \"recon-all\"}": 4, "provenance:{\"step\": \"rescale\"}": 1}

## 9 · fsl_vbm

design.mat and design.con files specifying the cross-subject statistical model, with row order matching the image order from imglob.

原文引用：create your design.mat and design.con in your FSL-VBM directory; see the randomise manual

审核版标准：{"template": "product_present", "parameters": {"slot": "design", "type": "type:StatsTable.DesignMatrix"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 3}

## 11 · fsl_vbm

All different populations included in the study must be represented in the template construction.

原文引用：All your different populations included in this study MUST be represented in the template construction.

审核版标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：运行/接口失败，单列环境或输出结构问题；主模板与审核版开发集标准不一致

票数：{}

## 14 · fsl_vbm

Check brain-extracted images (*_brain.*) in the struc directory after fslvbm_1_bet.

原文引用：CHECKING the brain images (*_brain.*) in your struc directory

审核版标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：运行/接口失败，单列环境或输出结构问题；主模板与审核版开发集标准不一致

票数：{}

## 15 · fsl_vbm

Check the template_GM_4D image in struc with the movie loop in fsleyes after template creation.

原文引用：CHECK the template_GM_4D image in struc with the movie loop in fsleyes.

审核版标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：运行/接口失败，单列环境或输出结构问题；主模板与审核版开发集标准不一致

票数：{}

## 16 · fsl_vbm

Check the 4D image of modulated registered GM images (GM_mod_merg) using the movie loop in fsleyes after fslvbm_3_proc.

原文引用：final CHECK of the 4D image of modulated registered GM images GM_mod_merg using the movie loop in fsleyes.

审核版标准：{"template": "advisory", "parameters": null}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：运行/接口失败，单列环境或输出结构问题；主模板与审核版开发集标准不一致

票数：{}

## 19 · global_surface_folding

White matter surface mesh of the cortical ribbon.

原文引用：our proposed method requires the bounding pial and white matter surfaces of the cortical ribbon as input

审核版标准：{"template": "product_present", "parameters": {"slot": "white", "type": "type:Surface.White"}}

预测：{"decision": "provider_error", "template": null, "parameters": null}

原因：运行/接口失败，单列环境或输出结构问题；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{}

## 20 · global_surface_folding

Point coordinates for convex hull computation.

原文引用：Coordinates of points to construct a convex hull from

审核版标准：{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 5}

## 21 · global_surface_folding

Cortical thickness estimate (average) for scaling law.

原文引用：we only had numerical values for the total and exposed surface area, as well a average cortical thickness estimates

审核版标准：{"template": "product_present", "parameters": {"slot": "thickness", "type": "type:SurfaceMetric.Thickness"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 4, "product_present:{\"slot\": \"thickness\", \"type\": \"type:SurfaceMetric.Thickness\"}": 1}

## 33 · hcp_structural_pipeline

T1/T2 structural images are processed by the three structural batch scripts.

原文引用：处理T1/T2结构像

审核版标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 5}

## 36 · local_gyrification

The pial surface file (?h.pial) for the subject, produced by the recon-all -all stream.

原文引用：usage of the -localGI feature assumes that a subject has already been processed by the freesurfer {{{recon-all -s <subjid> -all}}} stream, such that the ?h.pial surface files exist

审核版标准：{"template": "product_present", "parameters": {"slot": "pial", "type": "type:Surface.Pial"}}

预测：{"decision": "review", "template": "provenance", "parameters": {"step": "recon-all"}}

原因：未接受：support=0.6, margin=0.19999999999999996, answered=5；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"provenance:{\"step\": \"recon-all\"}": 3, "product_present:{\"slot\": \"pial\", \"type\": \"type:Surface.Pial\"}": 2}

## 38 · local_gyrification

MATLAB with Image Processing Toolbox and $FREESURFER_HOME/matlab in the MATLAB path.

原文引用：MATLAB is required to use the -localGI feature. Also, you will need their Image Processing Toolbox.

审核版标准：{"template": "software", "parameters": {"commands": ["matlab"]}}

预测：{"decision": "accepted", "template": "software", "parameters": {"commands": ["image", "matlab"]}}

原因：逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"software:{\"commands\": [\"image\", \"matlab\"]}": 5}

## 40 · local_gyrification

MATLAB and its Image Processing Toolbox must be installed and accessible.

原文引用：MATLAB is required to use the -localGI feature. Also, you will need their Image Processing Toolbox.

审核版标准：{"template": "software", "parameters": {"commands": ["matlab"]}}

预测：{"decision": "accepted", "template": "software", "parameters": {"commands": ["image", "matlab"]}}

原因：逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"software:{\"commands\": [\"image\", \"matlab\"]}": 5}

## 41 · local_gyrification

The MATLAB path must include $FREESURFER_HOME/matlab, set up in ~/matlab/startup.m.

原文引用：You will also need $FREESURFER_HOME/matlab in your matlab path set up in your ~/matlab/starup.m script.

审核版标准：{"template": "software", "parameters": {"commands": ["matlab"]}}

预测：{"decision": "accepted", "template": "software", "parameters": {"commands": ["freesurfer", "matlab"]}}

原因：逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"software:{\"commands\": [\"freesurfer\", \"matlab\"]}": 4, "software:{\"commands\": [\"matlab\"]}": 1}

## 47 · macaque_civet

The pipeline is designed for macaque brains and uses a length scale of 0.4 relative to human brain size.

原文引用：A length scale of 0.4 was derived from the cubic root of the macaque-to-human volume ratio

审核版标准：{"template": "attr_in", "parameters": {"slot": "T1", "attr": "species", "values": ["macaque"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：未接受：support=0.4, margin=0.0, answered=4；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 2, "scale_check:{\"metric\": \"length scale (macaque-to-human volume ratio)\"}": 2}

## 53 · macaque_civet

The pipeline is not validated for species other than macaques; adaptations for other primates would require appropriate length scales and templates.

原文引用：Further adaptations of the pipeline to other non-human primate brains should be straightforward by introducing the appropriate length scales and supplying species specific templates.

审核版标准：{"template": "attr_in", "parameters": {"slot": "T1", "attr": "species", "values": ["macaque"]}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 4}

## 56 · nhp_macapype

Input data must be in BIDS format, with T1w and T2w images expected.

原文引用：All the data have to be in BIDS format to run properly

审核版标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 4}

## 57 · nhp_macapype

T1 weighted images are expected with the _T1w BIDS extension.

原文引用：_T1w (BIDS) extension is expected for T1 weighted images

审核版标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 4, "product_present:{\"slot\": \"T1\", \"type\": \"type:Volume.T1\"}": 1}

## 71 · samseg_segmentation

All input volumes must be co-registered with each other and have the same image grid size and voxel dimensions.

原文引用：the only requirement is that all input volumes are co-registered with each other, and have the same image grid size and voxel dimensions

审核版标准：{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：未接受：support=None, margin=None, answered=5；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{}

## 73 · samseg_segmentation

For longitudinal processing, all time points must be co-registered and reformatted to the same image grid, using an unbiased reference template.

原文引用：longitudinal SAMSEG expects all its input images to have been co-registered and reformatted to the same image grid beforehand

审核版标准：{"template": "attr_equal", "parameters": {"slots": ["T1", "timepoints"], "attrs": ["space", "voxel_size"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：未接受：support=0.2, margin=0.2, answered=5；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 1}

## 75 · samseg_segmentation

For multi-contrast input, all volumes must be co-registered and have the same image grid size and voxel dimensions.

原文引用：all input volumes are co-registered with each other, and have the same image grid size and voxel dimensions

审核版标准：{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：未接受：support=None, margin=None, answered=5；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{}

## 78 · samseg_segmentation

Verify that all input volumes are co-registered and have the same image grid size and voxel dimensions.

原文引用：the only requirement is that all input volumes are co-registered with each other, and have the same image grid size and voxel dimensions

审核版标准：{"template": "attr_equal", "parameters": {"slots": ["T1", "volumes"], "attrs": ["space", "voxel_size"]}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：未接受：support=None, margin=None, answered=4；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{}

## 82 · samseg_segmentation

The first time the MS lesion module is run, the user may be prompted to install Tensorflow.

原文引用：The first time you run this module, you may be prompted to install Tensorflow

审核版标准：{"template": "advisory", "parameters": null}

预测：{"decision": "review", "template": "software", "parameters": {"commands": ["tensorflow"]}}

原因：未接受：support=0.6, margin=0.19999999999999996, answered=5；主模板与审核版开发集标准不一致

票数：{"software:{\"commands\": [\"tensorflow\"]}": 3, "advisory": 2}

## 86 · surface_annotation_roi

Verify that the number of morphometry values matches the number of vertices in the annotation.

原文引用：labelsndarray, shape (n_vertices,)

审核版标准：{"template": "attr_equal", "parameters": {"slots": ["annotation", "metric"], "attrs": ["mesh"]}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 3, "attr_equal:{\"attrs\": [\"mesh\"], \"slots\": [\"annotation\", \"metric\"]}": 1}

## 95 · surface_mesh_area

Verify that the mesh is in triangular format as expected by read_geometry.

原文引用：Read a triangular format Freesurfer surface mesh.

审核版标准：{"template": "advisory", "parameters": null}

预测：{"decision": "review", "template": "attr_in", "parameters": {"slot": "surface", "attr": "mesh", "values": ["triangular"]}}

原因：未接受：support=0.6, margin=0.19999999999999996, answered=5；主模板与审核版开发集标准不一致

票数：{"attr_in:{\"attr\": \"mesh\", \"slot\": \"surface\", \"values\": [\"triangular\"]}": 3, "advisory": 2}

## 99 · surface_reconstruction_qc

T1-weighted anatomical image(s) in DICOM or other native scanner format.

原文引用：the raw data from the scan must be converted into a format recognized by FreeSurfer

审核版标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "review", "template": "advisory", "parameters": null}

原因：未接受：support=0.4, margin=0.0, answered=4；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"advisory": 2, "product_present:{\"slot\": \"T1\", \"type\": \"type:Volume.T1\"}": 2}

## 101 · surface_reconstruction_qc

Output volumes from recon-all processing, including T1.mgz, brainmask.mgz, and surface files.

原文引用：load the T1 and brainmask images as underlays in freeview, and overlay the white and pial surfaces

审核版标准：{"template": "product_present", "parameters": {"slot": "T1", "type": "type:Volume.T1"}}

预测：{"decision": "review", "template": "provenance", "parameters": {"step": "recon-all"}}

原因：未接受：support=0.6, margin=0.19999999999999996, answered=5；主模板与审核版开发集标准不一致；可执行/非可执行判定不一致；逐条规范键不一致（严格字符串，不增设同义规则）

票数：{"provenance:{\"step\": \"recon-all\"}": 3, "advisory": 2}
