# 本次评测的运行与审计脚本记录

这些文件是实际使用的脚本副本，ROOT/WORK 为开发机路径。规范模型调用入口是 tools/knowledge/run_condition_canonicalization.py。

- audit_results.py：只读核验评分、冻结、无标准答案泄漏、预算、既有回答保留、受保护文件和密钥脱敏，不调用模型。
- build_diagnostics.py：只从已保存回答生成 token 表和逐条诊断，不调用模型；会追加 REPORT.md，已有结果请勿重复追加。
- complete_budget.py：本次用户授权累计 1000 请求后的补跑记录；原批次最多 800，单独补跑最多 200，仅补预算遗漏而未收到模型回答的条目。实际补跑 62 次，全部既有回答保持原样。

原始 HTTP 账本与检查点只在开发机和本地交付保留；公开分支保存汇总、结构化结果、脱敏 token 表和冻结/审计记录。
