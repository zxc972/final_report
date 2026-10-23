# Claude 盲标注交接

只向标注者提供本目录。这里没有算法输出、分数、开发集标签或错误清单。
请依据陈述、原文上下文和 annotation_schema.json 的通用定义逐条标注一个
主模板与参数；建议性参数为 null。不要调用或查阅规范化算法的预测。
逐条记录歧义、超出引文的内容及待用户决定项；不要为凑可执行条件发明参数。
annotation_sheet.csv 的答案列目前为空，statements_unlabelled.json 未含 gold。

标注后保留原始陈述 ID、来源、引文和字段，交还 JSON/CSV。用户通知后再做
独立审核、冻结标注 SHA，并运行 full_v2、k1_v2、direct_v2、retrieval_only。
本轮不生成独立集金标准，也不对它运行算法。当前状态是 ready_for_Claude。

原请求中的 Workbench -surface-area 按官方命令名 -surface-vertex-areas 记录。
既有开发集用过的 NMT v2 总览页已排除；使用独立的 CHARM 说明和安装程序文档，不把 v2.1 默认值改写为 v2.0。
