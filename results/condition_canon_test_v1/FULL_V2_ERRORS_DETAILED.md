# full_v2 错误清单与逐样本检查

本文件为固定结果的离线诊断；无模型调用、调参或标准答案修改。

## 1003 · independent_fastsurfer

An optional binary lesion mask must be in the same space as the T1 input.

引文：Path to a binary lesion mask in the same space as the T1 input.

冻结标准：{"template": "advisory", "parameters": null}

标注说明：可选输入；“与 T1 同一空间”只在提供病灶掩膜时适用。【待决定】若把条件性要求也算，可标 attr_equal(T1, mask; space)

预测：{"decision": "accepted", "template": "attr_equal", "parameters": {"slots": ["mask", "T1"], "attrs": ["space"]}}

具体解释：可选病灶掩膜启用时确有空间一致要求；模型5/5投attr_equal。冻结标注把可选输入整体记为建议性，本条待用户决定。

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则；该条仍待用户决定，主报告按文件标注计分，39条敏感性集合已排除

票数：{"attr_equal:{\"attrs\": [\"space\"], \"slots\": [\"T1\", \"mask\"]}": 5}

逐样本解析/类型检查：

```json
[
  {
    "sample": 1,
    "replacement_of": null,
    "request_id": "d461538747fc46e59af8ca7a54ecd40f",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "attr_equal",
    "raw_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "normalised_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "problems": []
  },
  {
    "sample": 2,
    "replacement_of": null,
    "request_id": "430cad44f95242ce827cd0d42bf74f9a",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "attr_equal",
    "raw_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "normalised_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "problems": []
  },
  {
    "sample": 3,
    "replacement_of": null,
    "request_id": "ae9a0d83f6234c62b017f667fcc35142",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "attr_equal",
    "raw_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "normalised_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "problems": []
  },
  {
    "sample": 4,
    "replacement_of": null,
    "request_id": "e677634fe8ef4e96a8b901380a0576cd",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "attr_equal",
    "raw_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "normalised_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "problems": []
  },
  {
    "sample": 5,
    "replacement_of": null,
    "request_id": "6ba76a70223f4a72a720a72580405054",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "attr_equal",
    "raw_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "normalised_parameters": {
      "slots": [
        "mask",
        "T1"
      ],
      "attrs": [
        "space"
      ]
    },
    "problems": []
  }
]
```

## 1011 · independent_fastsurfer

Unless --ignore_fs_version is set, the program checks the FreeSurfer version and terminates if the supported version is not sourced.

引文：--ignore_fs_version Switch on to avoid check for FreeSurfer version.
Program will terminate if the supported version
(see recon-surf.sh) is not sourced.

冻结标准：{"template": "software", "parameters": {"commands": ["freesurfer"]}}

标注说明：要求加载受支持版本的 FreeSurfer；版本号未在引文中给出，不发明版本参数

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

具体解释：模型5/5将版本检查及可跳过选项视为建议性；冻结标准要求表达FreeSurfer软件前置条件，属于模板边界判断。

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则

票数：{"advisory": 5}

逐样本解析/类型检查：

```json
[
  {
    "sample": 1,
    "replacement_of": null,
    "request_id": "fa267291a5e640f396339fc64098db54",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 2,
    "replacement_of": null,
    "request_id": "a47d410993664bd7be763914bf1b784c",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 3,
    "replacement_of": null,
    "request_id": "9e6ca1049f8f43b383223e8d5fa5560e",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 4,
    "replacement_of": null,
    "request_id": "9c1b25ae3f3c4e83ba853f93283a00f6",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 5,
    "replacement_of": null,
    "request_id": "c8703c1788ef48728d634e0d66f83fb9",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  }
]
```

## 1017 · independent_fastsurfer

--no_surfreg skips surface registration, but sphere.reg is needed for cross-subject statistical analysis of thickness maps.

引文：sphere.reg will be needed for any cross-subject statistical analysis of thickness maps

冻结标准：{"template": "product_present", "parameters": {"slot": "surface", "type": "type:Surface.SphereReg"}}

标注说明：跨被试厚度统计需要 sphere.reg。【待决定】该句出现在 exceptions 字段且以下游分析为条件

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

具体解释：sphere.reg的下游统计输入要求被选项说明语境覆盖：3票advisory、1票product_present、1票provenance；本条待用户决定。

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则；该条仍待用户决定，主报告按文件标注计分，39条敏感性集合已排除

票数：{"advisory": 3, "product_present:{\"slot\": \"surface\", \"type\": \"type:Surface.SphereReg\"}": 1, "provenance:{\"step\": \"recon-all\"}": 1}

逐样本解析/类型检查：

```json
[
  {
    "sample": 1,
    "replacement_of": null,
    "request_id": "739eed9eeebb4b2997f20756d3e0dbdf",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "product_present",
    "raw_parameters": {
      "slot": "surface",
      "type": "type:Surface.SphereReg"
    },
    "normalised_parameters": {
      "slot": "surface",
      "type": "type:Surface.SphereReg"
    },
    "problems": []
  },
  {
    "sample": 2,
    "replacement_of": null,
    "request_id": "7b82f63997ac4becb6bf647bc03113ac",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 3,
    "replacement_of": null,
    "request_id": "9b5f5c1abf68427194bea6b636f61da9",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "provenance",
    "raw_parameters": {
      "step": "recon-all"
    },
    "normalised_parameters": {
      "step": "recon-all"
    },
    "problems": []
  },
  {
    "sample": 4,
    "replacement_of": null,
    "request_id": "6b37b7925fbb47faaf57ccc4783ea2cb",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 5,
    "replacement_of": null,
    "request_id": "e9bbbc88d84b4d1d84188ac0821ff6a8",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  }
]
```

## 1020 · independent_fs_glmfit_group

Global design matrix specified with a FreeSurfer Group Descriptor File (FSGDF).

引文：Specify the global design matrix with a FreeSurfer Group Descriptor File (FSGDF).

冻结标准：{"template": "product_present", "parameters": {"slot": "design", "type": "type:StatsTable.DesignMatrix"}}

标注说明：FSGD 定义全局设计矩阵

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

具体解释：描述式FSGDF设计矩阵输入说明被模型5/5判为建议性，未转成design产物需求。

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则

票数：{"advisory": 5}

逐样本解析/类型检查：

```json
[
  {
    "sample": 1,
    "replacement_of": null,
    "request_id": "21203c6d31c44f10aa91b85b73538fba",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 2,
    "replacement_of": null,
    "request_id": "9195881076164101b5b1fa11f162e755",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 3,
    "replacement_of": null,
    "request_id": "d4335a0d56db4d33a163d87787c64d90",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 4,
    "replacement_of": null,
    "request_id": "c5e6f80fc2934643a53f1542a5612b5b",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 5,
    "replacement_of": null,
    "request_id": "30184bf839984f4e9fcc87142f154c60",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  }
]
```

## 1037 · independent_workbench_area_stats

The percentile must be between 0 and 100.

引文：must be between 0 and 100

冻结标准：{"template": "advisory", "parameters": null}

标注说明：参数取值约束（命令行）

预测：{"decision": "accepted", "template": "plausibility", "parameters": {"metric": "percentile"}}

具体解释：模型5/5把命令行percentile参数的合法范围0–100判为数据指标plausibility；冻结标准将命令用法归建议性。

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则

票数：{"plausibility:{\"metric\": \"percentile\"}": 5}

逐样本解析/类型检查：

```json
[
  {
    "sample": 1,
    "replacement_of": null,
    "request_id": "3cd702196fcd48c0a9aa904b85cc20de",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "plausibility",
    "raw_parameters": {
      "metric": "percentile"
    },
    "normalised_parameters": {
      "metric": "percentile"
    },
    "problems": []
  },
  {
    "sample": 2,
    "replacement_of": null,
    "request_id": "b9019cd5215d4104976b443b1fe5dcce",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "plausibility",
    "raw_parameters": {
      "metric": "percentile"
    },
    "normalised_parameters": {
      "metric": "percentile"
    },
    "problems": []
  },
  {
    "sample": 3,
    "replacement_of": null,
    "request_id": "5c113f1a79a64d9ab02b4bdaf0acb550",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "plausibility",
    "raw_parameters": {
      "metric": "percentile"
    },
    "normalised_parameters": {
      "metric": "percentile"
    },
    "problems": []
  },
  {
    "sample": 4,
    "replacement_of": null,
    "request_id": "d74fceac3de34121b934ec273e5354d4",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "plausibility",
    "raw_parameters": {
      "metric": "percentile"
    },
    "normalised_parameters": {
      "metric": "percentile"
    },
    "problems": []
  },
  {
    "sample": 5,
    "replacement_of": null,
    "request_id": "60b1c56b2cc9437bb09315299f880e4c",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "plausibility",
    "raw_parameters": {
      "metric": "percentile"
    },
    "normalised_parameters": {
      "metric": "percentile"
    },
    "problems": []
  }
]
```

## 1041 · independent_nmt_v2_charm

The CHARM is defined in the coordinates/space of the NMT v2 template.

引文：This atlas is defined in the coordinates/space of the NMT v2
template

冻结标准：{"template": "attr_in", "parameters": {"slot": "annotation", "attr": "space", "values": ["NMT_v2"]}}

标注说明：CHARM 定义在 NMT v2 空间：使用 CHARM 分区的数据须处于 NMT v2 空间。【待决定】也可视为图谱自身属性的描述（建议性）

预测：{"decision": "advisory", "template": "advisory", "parameters": null}

具体解释：4票advisory；另1票attr_in的空间值不在现有受控域，被类型检查拒绝。冻结标准要求annotation.space=NMT_v2，本条待用户决定。

原因：主模板与冻结标准不一致；可执行/非可执行判定与冻结标准不一致；逐条严格规范键不一致；保留原字符串，不增加同义规则；类型/词表检查排除了部分样本：{"attr_in": 1}；实际样本检查结果：values outside the space domain；该条仍待用户决定，主报告按文件标注计分，39条敏感性集合已排除

票数：{"advisory": 4}

逐样本解析/类型检查：

```json
[
  {
    "sample": 1,
    "replacement_of": null,
    "request_id": "48fc1c1197c546b2a70f962588b4d1eb",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 2,
    "replacement_of": null,
    "request_id": "a0e67f72e4734cb6a7c98b8e7a067137",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 3,
    "replacement_of": null,
    "request_id": "f648052d75cd49a1a65f18f18a348221",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "attr_in",
    "raw_parameters": {
      "slot": "annotation",
      "attr": "space",
      "values": [
        "NMT2"
      ]
    },
    "normalised_parameters": {
      "slot": "annotation",
      "attr": "space",
      "values": [
        "NMT2"
      ]
    },
    "problems": [
      "values outside the space domain"
    ]
  },
  {
    "sample": 4,
    "replacement_of": null,
    "request_id": "2f6e9432e82049158e51f177b355a41d",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  },
  {
    "sample": 5,
    "replacement_of": null,
    "request_id": "f30d23f839dc42bebecea79931ccd230",
    "finish_reason": "stop",
    "parseable": true,
    "raw_template": "advisory",
    "raw_parameters": {},
    "normalised_parameters": null,
    "problems": []
  }
]
```
