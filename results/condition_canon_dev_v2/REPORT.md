# 第十七轮：条件规范化开发集

108 条是开发集，不能作为独立正式测试集。6 条待决定暂按用户指定的 Claude 建议计分，未改变审核状态。

| 组别 | 模板准确率 % | 可执行 P/R/F1 % | 非可执行 P/R/F1 % | 规范键 P/R/F1 % | 审核队列 | 新 HTTP | 已知 token |
|---|---:|---|---|---|---:|---:|---:|
| v1_full | 47.22 | 57.14/12.50/20.51 | 72.28/96.05/82.49 | 14.29/4.55/6.90 | 48 | 0 | 0 |
| v1_k1 | 55.56 | 27.59/25.00/26.23 | 69.62/72.37/70.97 | 3.57/4.55/4.00 | 0 | 0 | 0 |
| v1_retrieval_only | 13.89 | 31.68/100.00/48.12 | 100.00/9.21/16.87 | 0.00/0.00/0.00 | 0 | 0 | 0 |
| v1_direct | 62.04 | 43.75/43.75/43.75 | 76.32/76.32/76.32 | 3.33/4.55/3.85 | 0 | 0 | 0 |
| full_v2 | 75.00 | 92.86/40.62/56.52 | 79.79/98.68/88.24 | 75.00/40.91/52.94 | 14 | 592 | 1384457 |
| k1_v2 | 79.63 | 73.91/53.12/61.82 | 82.35/92.11/86.96 | 66.67/63.64/65.12 | 10 | 110 | 315507 |
| direct_v2 | 84.26 | 81.48/68.75/74.58 | 87.65/93.42/90.45 | 4.17/4.55/4.35 | 0 | 111 | 290289 |

v1 四组只更换标准答案重算，历史预测文件摘要已冻结，没有新调用。retrieval_only 不填参数，规范键按原评分器空集合零分约定报告。

v2 模型设置：{"endpoint_host": "inferaiapi.com", "endpoint_path": "/v1", "model": "deepseek-v4.1-flash", "temperature": 0.7, "timeout": 180, "max_tokens": 8192, "max_attempts": 3, "thinking": {"type": "disabled"}, "response_format": {"type": "json_object"}}

使用量：{"logical_calls": 740, "http_attempts": 813, "successful_requests": 732, "failed_requests": 81, "unfinished_requests": 0, "length_limited_responses": 0, "historical_null_length_responses": 0, "unknown_usage_requests": 81, "input_tokens": 1776210, "output_tokens": 214043, "total_tokens": 1990253, "observed_models": ["deepseek-v4.1-flash"]}

截断补采：{"full_v2": 0, "k1_v2": 0, "direct_v2": 0}

full_v2 错误 30 条，见 FULL_V2_ERRORS.md。冻结 SHA：1eb334ccc1e0762fc582aaa0b5ebc0eb4d9344aaf6b35d2aebf6f8747ba09808


## 完整运行核验

合入提交：79d6bcb（审核版标签）和 765bae2（v2 算法）。运行器与源卡工具提交 df94959；源码与盲标注材料已通过完整默认后端测试：894 passed、14 skipped、59 subtests passed，144 条既有警告。

评分口径：模板准确率采用最佳提案（包括 review）；可执行正类仅 accepted 且非 advisory。review/拒绝/错误按未接受计入负类，因此负类不等于显式 advisory。规范键按 (method, template, parameters) 去重，严格匹配，不补做同义词映射。

累计 HTTP 请求（含重试/补采/源卡抽取）：819/1200；开发集 813，源卡抽取 6。

已知 token：输入 1811636，输出 220957，合计 2032593；完整 usage 未知 83 次，未当作零计账。

实际返回：严格 JSON 对象 684 条，空文本 0 条，其他非对象/无效 JSON 52 条；非 length 的空文本未补采。length 0 次；报告推理 token 大于零 11 次、带非空 reasoning_content 190 次。因此关闭思考是请求设置，网关没有在所有响应上一致遵守；8192 上限和实际 finish_reason 已逐次记录。 严格 JSON 统计按完整 content 解析；算法沿用 bundle 从文本中提取对象的解析器，非严格 JSON 不直接等于算法解析失败。

环境/输出结构失败共 8 个组别条目，见 provider_and_structure_failures.json。完整 full_v2 错误见 FULL_V2_ERRORS_DETAILED.md；开发标签复核建议另列 annotation_review_notes_v2.md，未改 gold 或分数。

开发集原计划 756 个采样槽位；实际启动 740 个；截断补采 0 次。full_v2 的 8 条接口失败提前终止了后续共 16 个槽位，未重新采样替换它们。

为减轻早期限流，仅调整传输发包节奏；调整前 124 次请求全部有结束记录，18 条已完成预测及所有已有响应保持原样。freeze_history 记录旧/新摘要、账本前缀和预测摘要。算法文件与 bundle 完全相同，没有逐项调参或答案修补。

v1 与 v2 还存在思考/长度/JSON 调用设置差异；这里报告开发比较，不把改进单独归因于某一项修正。

## 独立测试候选集与 Claude 标注交接

| 方法 | 全卡陈述 | 待标注陈述 |
|---|---:|---:|
| independent_fastsurfer | 32 | 18 |
| independent_fs_glmfit_group | 27 | 14 |
| independent_workbench_area_stats | 19 | 6 |
| independent_nmt_v2_charm | 18 | 7 |

96 条引用与来源文本的精确位置均已核验，32 条补足引用或收窄语义范围，原卡与逐项修改记录保留。按与开发集相同的 inputs/conditions/checks/exceptions 字段取 45 条；方法与来源 URL 均不复用，精确规范化陈述/引文重复已检查。

Workbench 原请求 -surface-area 以官方命令 -surface-vertex-areas 记录。旧开发集已使用的 NMT 总览页被排除，采用未用过的官方 CHARM 与 Install_NMT 文档。

Claude 盲标注包含原文、陈述、空白表和通用规范，不含算法预测、分数或开发集标签。本环境没有可用 Claude 工具/CLI，交接包供转交，未声称已获得 Claude 标注。仅冻结源卡/交接文件，尚未生成或冻结独立测试 gold。后续收到标注冻结通知后再运行 full_v2/k1_v2/direct_v2/retrieval_only。

## 确认事项

没有输出密钥；没有部署、重启已有服务、访问/处理保留组、提交预处理、发起真实分析或覆盖知识层手写条件。独立集算法评测调用为 0。
