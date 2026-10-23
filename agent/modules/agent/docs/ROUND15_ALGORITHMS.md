# Round 15: CSP matching and AND-OR completion

本补充基于 `7f684bb`，合入 `round15_algorithms.bundle` 的 `151a95f`、`ac66f76`，并与第十五轮主任务的 `0d09847`（A3）和 `b8e27a1`（全局指标）共同验证。开发工作树为 `/data/xuancheng/agent_v1/round15_algorithms_source`。原服务及正在运行的主任务开发实例没有部署或重启。

## 接入改动

- `analysis_matching_adapter.py` 从 `method_requirements` 展开被试、半球、指标槽位；复用 `analysis_product_instances.profile_products` 的类型与属性。`analysis_csp_matching.solve` 决定所有候选绑定，`_candidate` 仅组装已选产物的公开上下文。每个解保存独立候选，保留软约束/空间偏好排序，并返回 `matching_stats.domain_sizes/search_nodes/pruned/truncated`。
- `method_requirements.json` 增加可审阅的匹配条件和已有输入选择策略：ROI/向量分析绑定 white 网格；全局 Measure 行优先 aparc.stats，再按已有字典序降级。更新 SHA-256。`cortex.label` 的稀疏索引数量不冒充完整网格大小；网格相等检查只作用于完整网格，subject/hemisphere 检查仍覆盖 cortex.label。
- 空域输出带类型、被试/半球/属性的 `missing_requirements`。非空域却无兼容解时报告 `matching_conflicts`，不把网格冲突伪装成文件不存在。画像读取错误不进入取值域；全局体积 OR 分支可降级到仍有效的 mask。
- `analysis_completion_adapter.py` 调用 `steps_from_workflow`、`plan` 和每次独立的 `optimal_plan`。十四步来自 `workflow_steps.json`，按被试实例化，双侧共用步骤只计一次；软件状态来自固定探针，未观察项保持未知。返回最小类型模型代价、顺序、原因链和精确校验。代价不一致写 `planning_optimality_mismatch` 事件，保持原返回不变。
- 封存同时绑定方法需求、工作流、产物类型、条件模板摘要。旧字段 `pipeline_dependencies_sha256` 为兼容保留，内容现对应工作流摘要；同时公开明确的 `workflow_steps_sha256`。旧统一代价搜索助手保留供历史单元测试，在线规划不再调用。

## 算法边界修复

补丁的基本测试通过后，接入测试覆盖并修复了：`constant`/默认参数启用条件的读取、`eligible_for_planning=false`、精确枚举的物种限制、输入属性交集而非覆盖、跨半球/网格不兼容、精确前向闭包只使用首个产物、多个目标共享步骤的全局代价，以及大样本单值域递归深度。AND-OR 保留非支配步骤集合后统一选最小代价；校验器仍独立枚举步骤子集。

## 新旧候选对照

比较基线为 `b8e27a1` 中的规划器，源文件 SHA-256：`e998c759eaf24c8182d319364fca74559b957bde4c7c5d7a9348d281130db9b0`。逐项比较方法、分区、被试、全部输入路径、保留标签键；忽略候选 ID 中因新合同摘要导致的正常变化。

| 离线案例 | 旧候选 | 新候选 | 绑定集合 |
|---|---:|---:|---|
| P1 区域汇总，合成 | 2 | 2 | 相同 |
| P2 凸包，合成 | 1 | 1 | 相同 |
| A3 不对称，合成 | 2 | 2 | 相同 |
| 组水平，8 人合成 | 1 | 1 | 相同 |
| 全局指标，合成 | 1 | 1 | 相同 |
| P1，IXI064 已保存画像 | 3 | 3 | 相同 |
| P2，IXI064 已保存画像 | 1 | 1 | 相同 |
| A3，IXI064 已保存画像 | 3 | 3 | 相同 |
| 全局指标，IXI064 已保存画像 | 1 | 1 | 相同 |

额外构造两项可解释的收紧：

1. 仅把左侧厚度产物空间声明改成 `fsLR_32k`，仍请求 stored/native。旧版按文件名返回 3 个候选；新版 0 个，触发 `unary.space`。未知空间仍可用于限定在原始输入内的描述，显式矛盾不能忽略。
2. 仅把左侧厚度产物物种改为 chimpanzee，登记仍为 human。旧版 3 个，新版 0 个，触发 `unary.species`。此修改只发生在离线画像副本。

## 冻结扰动实验

`experiments/planning_eval.py` 输入已观察画像、登记表和已记录软件探针。`planning_perturbations.json` 包含先编写的 **37 个状态及期望**，覆盖删除产物、网格、半球、空间、分区、物种声明、软件不可用，以及全局体积替代/可选双侧 pial。

先 `--freeze`，再 `--run`。冻结记录绑定画像、登记表、软件观测、规则、四份知识文档的摘要；输入或期望改变即拒绝运行。输出文件采用独占创建，不覆盖上次结果。冻结时间为 `2026-10-23 14:31:23 +08:00`，摘要 `ae150f9fc71d7278b94a20ebe33f736cfda3031807db66a58b321435d60c63b1`。原画像摘要 `61680db04360cfb5d872c5a2caa6c08bf44379e74e567d318a931a6790004b55`。

结果：候选正确 **37/37**，缺失需求正确 **37/37**，AND-OR 与精确最优一致 **37/37**。2 个状态出现非空方案，均为类型模型中单步 `rescale`，代价 1；这利用该步骤声明的厚度重算输出。软件/参数/尺度的未知项未被改写成已核实，方案不代表可直接执行。软件不可用只排除依赖该软件的步骤，仍可能存在替代方案。

```bash
python experiments/planning_eval.py --profile PROFILE.json --registry CATALOG.json \
  --subject IXI064 --software SOFTWARE.json --freeze frozen.json
python experiments/planning_eval.py --profile PROFILE.json --registry CATALOG.json \
  --subject IXI064 --software SOFTWARE.json --run frozen.json --output results.csv
```

真实画像及完整对照证据留在服务器 `round15_work`。CSV 只含算法判断、代价、步骤、时间、摘要，不含脑影像或形态学数值；模型调用 0，预处理提交 0。

## 验证及边界

- 原始 bundle 新测试：13 passed（匹配/规划 8、全局参考 5）。
- 合入基线：837 passed、14 skipped、59 subtests passed。
- 接入最终完整默认后端：**850 passed、14 skipped、59 subtests passed**，94.78 秒；144 条既有告警。
- 第一次基线的两项失败来自独立进程选择了不含 SciPy 的 Python；指定既有 `.venv-reference/bin/python` 后完整通过。没有因此修改参考算法或放宽判定。
- 受保护原始集合登记为 101 个，其中历史上只有 100 个映射到当前仓库；当前可映射 100 个全部保持原摘要。未声称重新核实无法映射的原主机文件。
- 本补充没有真实模型分析运行，不消耗主任务的 4 次真实分析授权；没有预处理提交、保留组处理、服务重启或 PR 合并。
- 精确枚举在每个被试的 14 步声明模型内校验；不等同于实测最短运行时间、解剖正确性或完整工作流可执行性验证。
