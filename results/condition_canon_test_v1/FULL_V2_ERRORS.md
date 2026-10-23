# full_v2 独立测试集错误清单

按模板、执行判定或逐条严格规范键任一不一致列出；未据此调参。

## 1003 · independent_fastsurfer（待用户决定项）

An optional binary lesion mask must be in the same space as the T1 input.

引文：Path to a binary lesion mask in the same space as the T1 input.

冻结标准：{"template": "advisory", "parameters": null}

预测：{"decision": "accepted", "template": "attr_equal", "parameters": {"slots": ["mask", "T1"], "attrs": ["space"]}}

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则

票数：{"attr_equal:{\"attrs\": [\"space\"], \"slots\": [\"T1\", \"mask\"]}": 5}

## 1011 · independent_fastsurfer

Unless --ignore_fs_version is set, the program checks the FreeSurfer version and terminates if the supported version is not sourced.

引文：--ignore_fs_version Switch on to avoid check for FreeSurfer version.
Program will terminate if the supported version
(see recon-surf.sh) is not sourced.

冻结标准：{"template": "software", "parameters": {"commands": ["freesurfer"]}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则

票数：{"advisory": 5}

## 1017 · independent_fastsurfer（待用户决定项）

--no_surfreg skips surface registration, but sphere.reg is needed for cross-subject statistical analysis of thickness maps.

引文：sphere.reg will be needed for any cross-subject statistical analysis of thickness maps

冻结标准：{"template": "product_present", "parameters": {"slot": "surface", "type": "type:Surface.SphereReg"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则

票数：{"advisory": 3, "product_present:{\"slot\": \"surface\", \"type\": \"type:Surface.SphereReg\"}": 1, "provenance:{\"step\": \"recon-all\"}": 1}

## 1020 · independent_fs_glmfit_group

Global design matrix specified with a FreeSurfer Group Descriptor File (FSGDF).

引文：Specify the global design matrix with a FreeSurfer Group Descriptor File (FSGDF).

冻结标准：{"template": "product_present", "parameters": {"slot": "design", "type": "type:StatsTable.DesignMatrix"}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则

票数：{"advisory": 5}

## 1037 · independent_workbench_area_stats

The percentile must be between 0 and 100.

引文：must be between 0 and 100

冻结标准：{"template": "advisory", "parameters": null}

预测：{"decision": "accepted", "template": "plausibility", "parameters": {"metric": "percentile"}}

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则

票数：{"plausibility:{\"metric\": \"percentile\"}": 5}

## 1041 · independent_nmt_v2_charm（待用户决定项）

The CHARM is defined in the coordinates/space of the NMT v2 template.

引文：This atlas is defined in the coordinates/space of the NMT v2
template

冻结标准：{"template": "attr_in", "parameters": {"slot": "annotation", "attr": "space", "values": ["NMT_v2"]}}

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则；类型/词表检查排除了部分样本：{"attr_in": 1}

票数：{"advisory": 4}
