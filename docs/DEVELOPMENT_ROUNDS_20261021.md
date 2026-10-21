# 2026-10-21：第一至第七轮开发代码同步

本次将受审工作树的 **94 个代码、配置和测试文件**合入源码快照，并更新说明、状态与完整性清单。它是开发进度归档，**未部署原服务，完整自主分析闭环仍未通过**。被试影像、分析产物、私有参考答案、完整 HTTP 轨迹、真实凭据及临时工作目录均未公开。

## 来源与复现边界

| 内容 | 原工作树提交 |
|---|---|
| 本次后端（含最新离线解析补修） | 703978766a8c5bfc6d11d976c7096da351a36594 |
| 本次前端 | 6ec6fc73522bebc8d917da4823e2a76266235f38 |
| 第七轮两次真实试跑的冻结后端 | d5a8c1e12189efd01bd0bd2603bb14c2ff55c4c7 |

这些是服务器独立工作树来源提交，不是本仓库历史提交。逐文件来源、摘要及同步基线在 [SNAPSHOT_MANIFEST.json](../SNAPSHOT_MANIFEST.json)。最新后端包含离线补修，不能把冻结后端的真实试跑归为补修版的实测成绩。

## 同步功能

| 模块 | 实现与入口 |
|---|---|
| 知识对照配置 | [profiles.json](../agent/modules/agent/knowledge_analysis/profiles.json)；默认 legacy_v13，未知配置拒绝加载；保留提示词分类与逐字节测试 |
| 图与原文入口 | search_evidence / read_evidence；按类型限制和回读原文、软件合同及方法证据 |
| 数据画像 | [analysis_data_profile.py](../agent/modules/agent/backend/analysis_data_profile.py) 与沙箱 worker；文件头、几何、标签、尺度和来源，缺项不猜测 |
| 可执行约束 | [constraint_probes.json](../agent/modules/agent/knowledge_analysis/constraint_probes.json)；探针实际观察与模型声明分开记录 |
| 计划与事件 | commit_plan、受保护版本与摘要、生产脚本路径门、增量 events 接口、前端依据卡与时间线 |
| 自动路由 | [agent_router.py](../agent/modules/agent/backend/agent_router.py)、共享对话上下文；保留显式实验模式 |
| 产物规划 | [analysis_product_planner.py](../agent/modules/agent/backend/analysis_product_planner.py)、[方法需求](../agent/modules/agent/knowledge_analysis/method_requirements.json)、[流程依赖](../agent/modules/agent/knowledge_analysis/pipeline_dependencies.json)；可行、可补产物及不可行原因 |
| 成熟操作库 | [primatex_ops.py](../agent/modules/agent/backend/primatex_ops.py) 的 10 个读取/汇总函数；按摘要只读挂载，Agent 仍生成完整分析程序 |
| 脑叶与标签 | [lobar_mapping.json](../agent/modules/agent/knowledge_analysis/lobar_mapping.json)；人类 DK 严格规则及明确 DKT 适配；猴脑 aparc 不套人类脑叶规则 |
| 前端 | 新布局、自动模式标记、真实过程栏、历史事件、Markdown 表格、错误摘要、未验证条件计数 |
| 纠错测试 | 内部审查假模型返回合法 JSON，保留原断言，并验证非法审查 JSON 仍失败 |

新增映射独立存放并附摘要。原 method_graph.json、research_v13 与冻结 LightRAG 索引不变；控制映射和接口字段不能算作新增审核科学概念。

## 当前真实试跑

第七轮按先 P1×2、至少一次完整验收通过才能继续 P2/P3 的规则执行：

- **P1 第一次**：Agent 生成代码，根据工具错误自行修改，第三次执行退出码 0；独立核对 **66/66 分区、330/330 标量**通过。但随后尝试不同于封存计划的代码路径，被正确拒绝，且未完成 finalize_artifacts，最终 blocked。
- **P1 第二次**：区域意图解析和候选选择失败，没有生产代码执行，最终 failed。
- **完整链路 0/2，数值核对 1/2**，未派发 P2×2 或 P3×1，未追加试跑。
- 两次共 **60 次 HTTP，均为 200**；已知输入 2,523,490 token（缓存 1,820,288）、输出 39,604，未知 usage 为 0。实际货币费用未核定。
- 7039787 仅离线修复精确分区名称优先级与实际 atlas 名的显式解析，**未重新调用真实模型验证**。

数值一致不等于科学适用性、专家图像 QC、物种确认、物理尺度核验或跨物种同源验证。原始失败证据在受控实验目录保留，本公开同步只提供聚合状态，不发布私有答案或被试产物。

## 本次验证

在隔离发布副本复用现有服务器依赖，未调用真实模型、未运行真实被试影像：

| 检查 | 结果 |
|---|---|
| 后端默认完整测试 | **554 passed / 0 failed / 12 skipped / 54 subtests passed** |
| 前端 Vitest | **42 passed，11 个文件** |
| TypeScript | npx tsc --noEmit，退出码 0 |
| 前端构建 | npm run build，退出码 0 |
| 保护核对 | 101 项摘要不变；legacy 提示词 7,652 字节及数值校验器摘要不变 |
| 完整性 | python tools/verify_snapshot.py；发布清单逐文件核对 |

12 项跳过包含需明确 opt-in 的真实沙箱测试和未装科学依赖的测试；本次没有为同步启动影像计算。构建保留现有大 chunk 提示，后端保留依赖弃用及测试辅助类收集警告。

第一次验证将源码平铺到临时目录，因缺 modules 命名空间产生 12 个收集错误；保留诊断，改用仓库包目录及 PYTHONPATH 后全部通过，没有修改产品源码或断言。554 项包含此前发布的 8 项回归测试；服务器受审工作树原有默认计数为 546 项。

## 配置与后续工作

默认仍为 legacy_v13。新环境先按 [运行依赖](SNAPSHOT.md) 准备外部镜像、隔离 Python、授权、embedding/tokenizer 和注册数据，再显式设置所需配置，例如：

    export AGENT_KNOWLEDGE_PROFILE=product_graph_planner

method_graph_gated 保留为条件检查对照。[experiment_budget.json](../agent/modules/agent/knowledge_analysis/experiment_budget.json) 的 30 次模型、60 次工具、8 次执行和 1,200 秒是开发实验配置；不能声称所有既有启动入口都已采用该预算，原服务常量未改。

下一步先审查计算成功后的收尾与封存路径绑定，再用单独限定的新批次验证完整链路；还需干净 Linux 部署与前端端到端验收。**本次没有部署、重启服务或补跑付费实验。**

机器状态见 [DEVELOPMENT_ROUNDS_20261021.json](DEVELOPMENT_ROUNDS_20261021.json)；较早同步记录保留在 [SYNC_20261021.md](SYNC_20261021.md)。
