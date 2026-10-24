# 第二十二轮执行报告（2026-10-24）

两条开发线已经合并。此前“预留已建、发送前绑定被拒”的故障在本轮矩阵回归及实际调用中未再出现，原生 ID、HTTP 与 usage 对齐通过；**原题完整链路通过 0/6 次**。局部表格核对通过与整次交付成功分开统计。

## 同步、合并与提交

获准的六文件同步前/后 SHA 已保存在 `results/round21_group_repair_20261024/post_stop_validation/sync_receipt.json`；本轮六文件到合并提交的完整谱系见 `results/round22_group_retest_20261024/six_file_lineage.json`。其中五个文件保持修正后原字节，SDK 测试按本轮要求补了激活/未激活的并发场景。

| 文件 | 真实复测冻结版 SHA-256 |
|---|---|
| `agent/modules/agent/backend/agent_chat_state.py` | `b0d204bff0c0036855501b4a1f1d0ace786dc79c94e6886c59351e2068f4d0c7` |
| `agent/modules/agent/backend/analysis_call_context.py` | `66901bdcb18b321dff82afff02d64a4edca0c6cfa48580fdc7cf2eb5581c1f2d` |
| `agent/modules/agent/backend/analysis_http_observer.py` | `ed9f6d3a7f61f5d94c4de0eaab3a2f45d5a984019f7a0b4202fa5ec3dcd81fec` |
| `agent/experiments/round21/dev_server.py` | `9472278c0eeaddec3e52b419aff0e4e9ea05f2428f60400e06ee4f8f9376779e` |
| `agent/experiments/round21/review_protected_changes.py` | `b6775dec3cd4bc4c281a1a355639835b5e06ba19b04d8e3a05e1d986df0a3af3` |
| `agent/modules/agent/tests/test_round21_sdk_http_observer.py` | `6c9227fb6fa7c38855bd0f738921d68ba45776f54a61e3f48870fb53050411f9` |

先把 GitHub 主线推进到 `70964d6`，ff 合入算法 2 的 `0f22d97`，再合并 `dev/round21-delivery` 的 `d6a5e74`，得到 `8a214cc95e0c34ddeceded461b94facc7244b139`。只有两个清单冲突，没有源码冲突：

- `SNAPSHOT_MANIFEST.json`：合并两边文件清单，保留归档身份和历史记录，按合并后的文件重算摘要。
- `PUBLICATION_MANIFEST.json`：依据合并后的已跟踪文件重新生成，没有整边覆盖另一边的产物。

新增并发 SDK 回归后冻结为 `3b61d7ca1b1493a0fd22c4a75d1cc9e08573b0d8`；6007 五项门禁通过后，已于 **04:53:08 UTC** 非强制推送并核验远端，随后才开始六次真实运行。所有六次始终使用此提交、同一环境和预算。第二十轮接入及交接包提交 `91807e5a690e86b57cd6cf989d33862248983453` 已于 **05:58:56 UTC** 推到相同主线；它在独立 `round20_source` 验证，不改变六次复测的冻结源码。最终报告推送号见交付回执和最终答复。

## 6007 上的五项门禁

| 项目 | 结果 |
|---|---|
| 冻结合并版全量默认后端 | 964 passed，16 skipped，59 subtests passed |
| 真实安装的 OpenAI SDK/httpx2、本地假服务器、未激活/已激活及并发 | 13 passed；原生 charge ID 与 usage 对齐 |
| 真实 route_message 经假服务器 | 合并定向回归共 48 passed；不存在 phantom charge/发送前绑定拒绝 |
| 脚本化假模型 + 真实 ToolNode + 真实 Singularity | G1、G2 各一条，2 passed |
| 受保护文件 | 既有 173 项相对修正后 Round21 全部相同；新增算法 2 文件 1 项 |

证据在 `results/round22_group_retest_20261024/offline_v2/`，包含完整 pytest 文本、SDK JUnit、原生绑定回归及受保护文件 SHA。门禁调用付费模型 0 次。第二十轮新增接入后的最终全量为 **974 passed、16 skipped、59 subtests passed**，新增接入/抽取 10 项、算法 8 项、SDK 13 项、定向 48 项及容器回路 2 项均通过，另见第二十轮报告。

## 原题与冻结配置

G1 原文：“这 20 名 IXI 被试，DKT 各分区平均皮层厚度与年龄的关系，控制性别。”

G2 原文：“比较这 20 名 IXI 被试中男性和女性的 DKT 各分区平均皮层厚度。”

`product_graph_planner` / `auto` / C 关闭 / `deepseek-v4-pro`；每次模型逻辑调用 30、工具 60、执行 8、执行时间上限 1200 秒，外层最多 3 轮。原有封存前规划上限 18、执行预留 9 保留。模型 HTTP 重试单列，不当作新的分析运行。没有改题、追加提示、提供人工分析代码或参考答案，也没有在批内修改代码、阈值或预算。

G1 前两次分别为执行后复审未完与封存前规划耗尽，G2 前两次分别为执行后规范产物缺失与封存前规划耗尽，均是不同链路；启动各自第三次之前尚未触发“同题连续两次同一链路”停跑条件，继续判定已保存。G2 第三次随后也在封存前达到规划上限，与第二次构成连续同链故障，已按停止规则及每题 3 次上限封存，没有追加运行。

## 每次运行

| 运行 | 状态 | 模型逻辑 / HTTP | 工具 / 执行 | 秒 | 内审 | 结论卡 |
|---|---|---:|---:|---:|---|---|
| R22_G1_1 | incomplete_review | 30 / 33 | 31 / 6 | 1038.8 | unreviewed | deferred |
| R22_G1_2 | failed | 18 / 18 | 19 / 0 | 380.9 | not_performed | deferred |
| R22_G1_3 | failed | 30 / 30 | 34 / 7 | 517.8 | not_performed | deferred |
| R22_G2_1 | failed | 30 / 30 | 35 / 7 | 486.1 | not_performed | deferred |
| R22_G2_2 | failed | 18 / 18 | 21 / 0 | 423.5 | not_performed | deferred |
| R22_G2_3 | failed | 18 / 19 | 19 / 0 | 445.0 | not_performed | deferred |

逐事件阶段序列见 `report/stages.csv`；这里保留宿主阶段转换（含重复修复），不删去失败阶段：

- **R22_G1_1**：unplanned → planned → sealed → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → finalized → executed_failed → sealed → executed_ok → finalized
- **R22_G1_2**：unplanned → planned
- **R22_G1_3**：unplanned → planned → sealed → executed_failed → sealed → executed_failed → sealed → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_failed → sealed → executed_ok → executed_failed → sealed
- **R22_G2_1**：unplanned → planned → sealed → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → executed_failed → sealed → executed_ok → executed_failed
- **R22_G2_2**：unplanned → planned
- **R22_G2_3**：unplanned → planned

两张表分别核对如下。未完成检查的行记 N/A；没有把“未核对”写成 0 差异。公开合同负责序列化/身份/格式，宿主独立参考另核对数值。

| 运行 | 表 | 行数/期望 | 公开合同 | 宿主核对 | 宿主身份差异 | 宿主数值差异 | 已核对标量 |
|---|---|---:|---|---|---:|---:|---:|
| R22_G1_1 | regional_values.csv | 1240/1240 | pass | pass | 0 | 0 | 6200 |
| R22_G1_1 | group_results.csv | 62/62 | pass | pass | 0 | 0 | 682 |
| R22_G1_2 | regional_values.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G1_2 | group_results.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G1_3 | regional_values.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G1_3 | group_results.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G2_1 | regional_values.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G2_1 | group_results.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G2_2 | regional_values.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G2_2 | group_results.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G2_3 | regional_values.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |
| R22_G2_3 | group_results.csv | N/A/N/A | not_performed | not_configured | N/A | N/A | N/A |

G1_1 的两表 1240/62 行均通过，宿主独立核对 6882 个标量，身份/数值差异分别为 0/0。内审先收到一次非 JSON 正文，结构重试后给出 revise（要求披露原方法硬阻断/替代等）；Agent 修订后，本次逻辑调用已达到 30，未完成后续复审，最终 `incomplete_review` / `unreviewed`，结论卡 deferred。其数值可作为已核对观察结果报告，不能计为完整科学交付。

G1_2、G2_2 在封存前的前置条件检查循环中达到 18 次规划调用，没有执行。G1_3、G2_1 在执行/产物修复阶段耗尽 30 次调用；G2_1 曾产生非规范命名的结果文件，之后又把封存脚本改写为打印 manifest/合同的诊断脚本，退出码 0 仍缺 `regional_values.csv` / `group_results.csv`，自动收尾按合同拒绝，未把诊断执行当成功。其他原始反馈、执行回执、内审与每次结论卡见 `report/failure_details.json`、`report/conclusion_cards.json`；原始请求/响应另行私有归档。

## G1 结果与文献方向

R22_G1_1：20 名被试，左右 31 个 DKT 分区，共 62 个检验；控制性别，年龄为连续变量，残差 df=17。BH-FDR 对全部 62 个分区统一校正，q<0.05 为 **32/62**；负向年龄估计为 **58/62（93.55%）**。封存宿主设计的 **d_min=0.645006370**，采用双侧 α=.05、power=.8 的正态近似并含性别协变量；这是标准化斜率的近似可检测效应，不是 FDR 校正后的效力。未增加站点/扫描仪协变量。

[Fjell 2009 原文](https://pubmed.ncbi.nlm.nih.gov/19150922/) 报告多个样本的广泛年龄相关变薄，额叶及颞上部较强，内侧颞叶和前扣带相对保留。本次仅作描述性方向对照，保留原分析：

| DKT 对照区域（合并两侧计数） | 负向 / 总数 | q<.05 | 平均年龄估计 mm/年 |
|---|---:|---:|---:|
| superior_and_inferior_frontal | 8/8 | 7 | -0.005191 |
| superior_temporal | 2/2 | 0 | -0.002440 |
| medial_temporal | 3/4 | 0 | -0.001972 |
| anterior_cingulate | 4/4 | 1 | -0.004088 |

额叶总体方向相符，颞上回同向但本样本未达到 FDR 显著；内侧颞叶无显著分区，前扣带仍有 1 个显著分区，不能简单称全部保留。未把颞顶交界硬配成一个 DKT 标签，也未验证空间图一致性。n=20、站点/场强混合及 AI 质控的局限保留；本次没有完成内审，结论仍 deferred。

R22_G1_2：两表未通过完整合同及宿主核对，FDR 数、方向比例和 d_min 的结果报告为 N/A，不用不合格的局部文件替代。

R22_G1_3：两表未通过完整合同及宿主核对，FDR 数、方向比例和 d_min 的结果报告为 N/A，不用不合格的局部文件替代。

## 调用计量

实际 `/api/agent/chat` 分析入口 **6 次**，原题各 3 次；模型逻辑调用 **144 次**，实际上游 HTTP **148 次**（含重试）。已知输入 token **2,345,319**、输出 **182,008**，合计 **2,527,327**；另有 **4 次 usage 未知**，没有按 0 计。模型、阶段、native logical/attempt ID、状态码、耗时及每次 token 见 `report/http_attempts.csv`。所有完成运行的原生预算与独立 HTTP 表逐条/汇总校验一致，未计量逻辑调用为 0。

第二十轮的小模型抽取独立计量：10/150 次 HTTP、9 次逻辑抽取，1 次 429；已知输入 51,525、输出 12,705 token，429 usage 未知，0 次截断；区域实验和条件规范化四组评测均未调用模型。

每次已知 token 与未知 usage 分布如下；未知值保留，不用于补零。

| 运行 | 已知输入 token | 已知输出 token | usage 未知 HTTP |
|---|---:|---:|---:|
| R22_G1_1 | 966,603 | 57,566 | 3 |
| R22_G1_2 | 145,261 | 25,707 | 0 |
| R22_G1_3 | 454,816 | 30,237 | 0 |
| R22_G2_1 | 463,209 | 20,899 | 0 |
| R22_G2_2 | 156,602 | 20,374 | 0 |
| R22_G2_3 | 158,828 | 27,225 | 1 |

148 次 HTTP 中有 144 次 200、2 次 504 和 2 次 429；144 条成功响应的 finish_reason 为 stop 或 tool_calls，没有 length 截断。重试仍受原预算与原生计量约束。

## 第二十轮交付与确认

第二十轮报告见 `docs/round20/ROUND20_REPORT.md`：C3 面积加权平均/最小 Dice 为 0.813008/0.633023，分配 146/148 标签；C1/C2 因缺 DKT annot 不可评，跨分辨率稳定性因只有 fsaverage 不可评。默认阈值、区域算法和关键词表未改。区域接入及复算已完成，几何复算复用相同模块，明确不声称独立实现。

9 张新方法卡共 191 条原文核对保留、1 条隔离，盲标包 83 条（inputs 33），未含算法输出/检索/预测/gold。交接包位于 `知识图谱/round14/condition_test_v2_annotation_packet/`；其清单 SHA-256 为 `caf821b66b1e841c595822ca94362fc7a025f969365168eb9c8803000a7239b0`，已冻结来源材料，尚未标注标准答案，也未运行四组。

真实运行全过程的 233 个源码/知识/驱动文件 SHA 不变；既有 10 个服务的 PID、启动时刻、cwd 和命令摘要均不变。批次授权已关闭，仅停止新建的 127.0.0.1:8122 开发进程；旧服务未部署或重启。没有提交预处理，没有释放新猕猴，没有处理 IXI 117 例保留组或 102311/105216。源码、报告和导出文件按实际配置凭据扫描后发布；原始 HTTP、逐被试表和私有参考不进入公开仓库。确认与停服回执见 `report/final_safety_audit.json`、`report/shutdown.json` 及发布扫描回执。

公开证据：`results/round22_group_retest_20261024/`。本地完整原始调用与结果归档：`知识图谱/round22/round22_private_evidence.tar.gz`；解析副本在 `round22/report_export/private/`，供本地复核。
