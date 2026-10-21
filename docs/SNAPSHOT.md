# 快照与运行依赖

## 快照来源

本次导出自服务器 /data/xuancheng/，核心代码为 agent/，最新研究知识为 agent_overnight_20261020/research_evidence_v13/。初始源目录没有 Git 历史；后续开发已在独立工作树记录版本。逐文件来源与摘要在 SNAPSHOT_MANIFEST.json，第一至第七轮源码与验证边界见 [开发同步说明](DEVELOPMENT_ROUNDS_20261021.md)。

发布时只读取服务器文件，没有停止或修改正在进行的开发。源文件导出后又逐一核对一次，确认该次快照内未发生并发变化。仓库不是服务器工作目录的自动镜像。2026-10-21 的增量同步保留初始快照时间，并在来源清单中记录各文件的新旧摘要；见 [本次同步与验证](SYNC_20261021.md)。

## 外部运行依赖

下列服务器资源没有放入 Git：

| 资源 | 当前代码使用的服务器路径/说明 |
|---|---|
| Apptainer 科学软件镜像 | /data/xuancheng/agent/PrimateX_1_7.sif，约 17GB |
| 隔离科学 Python 运行时 | /data/xuancheng/structural_env/runtime/python-analysis |
| FreeSurfer 授权 | /data/xuancheng/license.txt，由使用者自行准备 |
| 研究检索 Python | knowledge/research_v13/config.json 中的 python 路径，原值为 /data/xuancheng/retrieval_pilot_20261020/.venv/bin/python |
| Embedding 模型 | BAAI/bge-small-en-v1.5 对应已核对的 ONNX；版本与 SHA-256 见 environment/retrieval/model_provenance.json |
| Embedding / tokenizer 缓存 | worker.py 当前绑定 /data/xuancheng/retrieval_pilot_20261020/embedding_verified 与 tokenizer_cache |
| 分割模型和模板 | 参见 environment/manifests/、environment/recipes/ 和 environment/structural_env_README_zh.md |
| 数据 | 自行准备有权使用的数据，并配置 Agent 的注册数据根目录 |
| FastSurfer | 原项目保留了 agent/.gitmodules，但当前仓库没有根 .gitmodules 或 Git 子模块条目；clone --recurse-submodules 不会自动取得 FastSurfer，源码与模型需另行准备 |

agent/modules/agent/requirements-coding.lock 是后端服务依赖，科学分析依赖仍位于隔离运行时；environment/retrieval/installed_requirements.txt 记录检索实验环境。

## 配置知识检索

从根目录 .env.example 复制配置，设置真实绝对路径，并将其导入启动进程环境；启动脚本不会自动读取该文件。

    export AGENT_SOURCE_GRAPH_ROOT=/absolute/path/final_report/knowledge/software_graph
    export AGENT_RESEARCH_EVIDENCE_ROOT=/absolute/path/final_report/knowledge/research_v13

新增的 knowledge_analysis/research_release.json 与服务器原文件保持一致，默认指向服务器上的 v13，并校验 config.json 摘要。新机器必须显式设置上面的 AGENT_RESEARCH_EVIDENCE_ROOT；路径不可用时会报错，不会自动猜测替代知识库。显式设置为空可关闭研究知识检索。

config.json 和图谱包含校验摘要，保留了服务器原始值。迁移检索 Python 路径时，应使用正确的新环境；迁移 worker.py 中模型或 tokenizer 路径时，要重算 worker_sha256 及 snapshot_files 对应条目。修改任何受摘要保护的原文或图谱，也必须维护对应摘要，不能跳过完整性校验。

方法图谱与领域图谱里的来源都属于检索证据。Agent 仍应针对本次数据确认物种、空间、单位、前置条件和方法适用范围。

## 评测与审计

evaluation/task_index.json、任务说明和独立核对代码保留了核心实验定义。部分脚本和历史任务规格仍引用服务器上未公开的数据目录，不能仅在新机器克隆仓库后直接重放。

knowledge/method_audit/release_audit.json 是 v12 的历史抽取审计；当前 v13 的实时结构统计应读取 knowledge/research_v13/。历史独立审查材料不代表最新开发任务已经通过验收。

发布校验只验证快照完整性与静态可读性，没有重跑真实模型请求、容器计算或专家科学质控。

## 公开脱敏

公开版本已移除前端页面、旧启动脚本与原项目 README 中的固定访问令牌。启动脚本在未通过环境变量或参数提供令牌时，为本次启动生成随机令牌。早期 3 处访问令牌脱敏记录保留在历史；当前 App.tsx 已替换为本身不含令牌提示的受审版本，其余脱敏文件继续保留原始和发布摘要；详情见 SNAPSHOT_MANIFEST.json 的 publication_redactions。服务器原文件未被修改。

## 图谱无损归档

连接器多次无法传输大型 JSON，因此软件接口图以 graph.json.gz 无损保存。先运行 python tools/verify_snapshot.py，工具会在注册目录内解压生成 graph.json，核对压缩包摘要、解压长度及原始 SHA-256；解压后的字节与服务器原文件完全一致。原始 JSON 不直接提交到 Git，避免重复保存同一份图谱。Agent 和图谱读取器代码没有因此修改。

## 跨环境部署验收状态

目录迁移冒烟测试已确认方法图谱可以加载、搜索和回读；原文联合检索仍受旧 Python、worker 模型及 tokenizer 路径约束。执行器的 SIF、科学 Python 运行时和授权文件也沿用原服务器默认路径，启动脚本的镜像环境变量并未完整传入该执行器。当前不能仅凭克隆与安装后端依赖就宣称全链路可用。后续应统一这些配置、准备外部依赖，并在干净 Linux 环境验证真实 API、隔离执行、前端与下载流程。此次同步未修改服务器服务或这些运行时默认值。

## 今日开发配置

默认 AGENT_KNOWLEDGE_PROFILE 仍为 legacy_v13；新配置、计划门、操作库、前端事件及未通过项见 [今日开发同步](DEVELOPMENT_ROUNDS_20261021.md)。本次不是自动部署，原后端进程尚未加载新代码。
