# final_report

结构像分析 Agent 与知识图谱项目的核心源码快照。项目基于 PrimateX，覆盖人脑、猴脑及跨物种结构像分析中的知识检索、代码生成、隔离执行、任务管理、反馈诊断与结果审查。

初始快照时间：**2026-10-21T00:34:45.061928+08:00（Asia/Shanghai）**。**已同步今天第一至第七轮的 94 个代码、配置和测试文件**，包括知识配置、可执行约束、计划封存、自动路由、产物规划、底层操作库和新前端；来源与测试见 [今日开发同步说明](docs/DEVELOPMENT_ROUNDS_20261021.md)。

当前为开发快照，**第七轮完整分析闭环 0/2**；一次 66 分区数值核对通过，但产物收尾未完成。最新离线补修尚未真实模型重测，原服务未部署或重启。

## 目录

| 目录 | 内容 |
|---|---|
| agent/modules/agent/ | FastAPI 后端、Deep Agents/LangGraph 分析 Agent、检索工具、内部纠错与审查、后台任务、测试及 Skill 定义 |
| agent/modules/gui/ | React/TypeScript 前端、结果展示与下载、任务进度及取消、启动脚本 |
| agent/modules/neuro_pipeline/、agent/modules/primx_seg/、agent/workflows/ | 预处理、皮层重建、分割和工作流核心源码 |
| knowledge/research_v13/ | 最新方法图谱、领域图谱、登记原文、来源片段及冻结的 LightRAG 索引 |
| knowledge/software_graph/ | 软件接口、输入输出和参数合同图，含来源与构建脚本 |
| knowledge/domain_graph_base/ | 领域图谱基础层及来源 |
| knowledge/method_audit/、knowledge/method_extractions/ | 方法抽取、原文核对、修订与隔离记录 |
| evaluation/ | 分析任务定义、独立数值核对代码、检索对照实验摘要 |
| environment/ | 检索依赖、科学运行环境配方及版本清单 |
| tools/ | 知识构建、检索实验、快照导出与校验工具 |

## 图谱范围

- 方法图谱：**13 个方法、309 个节点、626 条关系**，节点包括输入要求、适用条件、分析步骤、验证检查、例外、产物和参数。
- 综合领域图谱：**2,239 个节点、7,256 条关系**，其中 **1,791 个为标签定义**。方法图谱节点已并入该图，不能把两个节点数相加当作独立知识量。
- 软件接口图：**3,415 个节点、7,638 条关系**，主要来自接口、参数与输出字段。
- 新增方法知识通过原文和方法图工具接入；冻结的原生 LightRAG 索引没有随新增方法重新建库。

这些是开发快照与证据记录。是否具备可靠的自主科学分析能力，应结合具体任务的数值、语义与图像质控结果判断。

## 使用入口

先阅读 [快照与运行依赖](docs/SNAPSHOT.md)、[分析 Agent 说明](agent/modules/agent/CODING_AGENT.md) 和 [后端文档](agent/modules/agent/README.md)。

解压软件接口图并校验源码和知识包（仅需 Python 标准库）：

    python tools/verify_snapshot.py

后端依赖安装和启动（Linux）：

    cd agent/modules/agent
    python3 -m venv .venv-coding
    . .venv-coding/bin/activate
    pip install -r requirements-coding.lock
    # 按根目录 .env.example 配置环境变量，并准备下述外部运行依赖
    bash start-coding-backend.sh

前端：

    cd agent/modules/gui/monkey-brain-frontend
    npm ci
    npm run dev

当前执行器沿用服务器上的 Apptainer/SIF、科学 Python 运行时和注册数据路径。知识检索也绑定本地 embedding 模型与 Python 环境。首次迁移需按 [运行依赖说明](docs/SNAPSHOT.md) 配置；本仓库保存源码与知识，不包含这些大型二进制依赖。

## 发布范围与校验

当前来源清单共 **770 个文件**，保留初始快照及后续增量来源。今天的 94 个源文件与受审工作树逐字节一致；早期公开脱敏、软件接口图无损归档和 8 项迁入测试的来源说明均保留。逐文件来源、权限、摘要及历史见 [SNAPSHOT_MANIFEST.json](SNAPSHOT_MANIFEST.json)。

本次公开发布排除了 API 密钥、实际 .env、FreeSurfer 授权文件、脑影像与受试者数据、分析产物、模型权重、容器镜像、虚拟环境、node_modules、完整 HTTP 轨迹及运行工作目录。保留的测试中含有明确的虚构凭据占位符。前端、启动脚本和原项目说明中的硬编码访问令牌已移除；启动器在未配置令牌时生成随机值。服务器部署未作修改。软件接口图以 graph.json.gz 无损保存，运行校验工具后会自动解压为 graph.json，并核对与服务器原文件完全相同的字节与摘要。

导出时二次确认源文件没有并发变化，并核对研究知识包中的全部 snapshot_files 摘要。发布前已检查 Python 语法和 JSON；前端 tsconfig.json 使用带注释 JSON 配置。本次隔离发布副本通过 **554 项后端测试、54 个子测试（12 项跳过）及 42 项前端测试**；TypeScript 与前端构建通过。复用现有依赖，没有调用真实模型或运行被试影像；全新机器部署及完整自主科学分析仍未验收。

## 许可与引用

PrimateX 原有 [LICENSE](agent/LICENSE)、[NOTICE](agent/NOTICE)、[CITATION.cff](agent/CITATION.cff) 和 [第三方声明](agent/docs/THIRD_PARTY_NOTICES.md) 均予以保留。第三方软件源码和论文、文档片段按各自来源的许可及引用要求使用；来源 URL 与证据范围保存在图谱与来源清单中。
