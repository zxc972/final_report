# 草稿标注审核提示

这些提示仅供用户审核，未修改 gold_draft_v1.json 或审核表，也不构成标注裁决。

- 第 58 条的陈述是 T2 weighted images，草稿参数却为 slot=T2、type=type:Volume.T1。请在正式标注时核对类型词表及这一映射是否有意如此。
- 第 84、85 条明确写了 Optionally，但草稿均标为 product_present。现模板没有 optional 参数；请核对可选输入与必需输入的标注原则。
- 第 92、95 条涉及三角网格格式要求，草稿均归 advisory；模型有时提出 attr_in。请按正式标注原则决定，当前评测继续使用原草稿。

逐条算法分歧见 FULL_ERRORS_DETAILED.md。方法内去重后的规范键评分与逐条模板/参数评分口径不同，不能用错误条目数直接推算 key F1。
