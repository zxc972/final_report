"""Post-run explanations from recorded answers only; no network or model calls."""
from pathlib import Path
import collections,csv,hashlib,json,re,sys
ROOT=Path('/data/xuancheng/agent_v1/round17_source')
sys.path.insert(0,str(ROOT))
from tools.knowledge import run_condition_canonicalization as base
from tools.knowledge import run_condition_canonicalization_v2 as run
out=ROOT/'results/condition_canon_dev_v2';independent=ROOT/'evaluation/condition_test_v1'
c=base.load_canon();vocab,_=run.load_vocab()
gold=json.loads((ROOT/'evaluation/condition_gold/gold_reviewed_v1.json').read_text());by_id={i['id']:i for i in gold['items']}
preds=json.loads((out/'predictions_full_v2.json').read_text());by_pred={p['id']:p for p in preds}
errors=json.loads((out/'full_v2_errors.json').read_text())
ev=[json.loads(x) for x in (out/'requests/calls.jsonl').read_text().splitlines()]
ends=[e for e in ev if e['event']=='end'];causes=collections.Counter();details=[]
for row in errors:
 p=by_pred[row['id']];item=by_id[row['id']];reasons=[];samples=[]
 for e in ends:
  if e['arm']!='full_v2' or e['item_id']!=item['id'] or e.get('status')!='ok':continue
  raw=e.get('text','');parsed=None;problems=[];normalised=None
  try:
   match=re.search(r"\{.*\}",raw or "",re.S)
   parsed=json.loads(match.group(0)) if match else None
   if not isinstance(parsed,dict):
    problems=['no JSON object decoded by bundled parser']
   else:
    template=str(parsed.get('template','advisory')).strip()
    if template in ('none',''):template='advisory'
    if template not in c.TEMPLATES:problems=['unknown template '+template]
    elif template!='advisory':
     normalised,problems=c.normalise_v2(template,parsed.get('parameters') or {},vocab)
     problems=problems or c.type_check_v2(template,normalised,gold['slots'],vocab)
  except (TypeError,ValueError,KeyError,AttributeError):problems=['unparseable or malformed parameter structure']
  samples.append({'sample':e['sample'],'finish_reason':e.get('finish_reason'),'answer':parsed if parsed is not None else raw,
                  'normalised_parameters':normalised,'type_problems':problems})
 if p['decision']=='provider_error':
  cause='provider_environment';reasons.append('接口传输尝试耗尽，没有生成完整条目预测；不归为算法语义错误。')
 elif p['decision']=='inference_error':
  cause='invalid_answer_structure';reasons.append('已记录的模型答案结构触发算法异常：'+p.get('runtime_error_type',''))
 elif p['decision']=='review':
  if p.get('support')==0.6 and 0 < 0.2-p.get('margin',0) < 1e-12:
   cause='template_mismatch_with_margin_boundary' if row['template_wrong'] else 'floating_point_margin_boundary';reasons.append('3/5 对 2/5 的票差在浮点计算中得到略小于 0.2 的值，触发 bundle 原有的 margin 阈值；本轮未改算法。主模板若与标准不同，即使修复数值边界，该模板分歧也仍然存在。')
  elif p.get('reason')=='no valid answer':
   cause='no_type_valid_answer';reasons.append('样本没有形成可用的类型合法答案；逐样本问题见下表。')
  else:
   cause='split_or_insufficient_votes';reasons.append('有效规范键的票数或票差不足，算法将最佳提案送审。')
  reasons.append(f"support={p.get('support')}, margin={p.get('margin')}, votes={json.dumps(p.get('votes',{}),ensure_ascii=False)}")
 elif row['template_wrong']:
  cause='template_mismatch';reasons.append(f"算法选择 {p.get('template')}，审核版标准为 {item['gold_template']}。")
 else:
  cause='parameter_key_mismatch'
 if row['statement_key_wrong'] and p.get('decision')=='accepted' and p.get('template')!='advisory' and item['gold_template']!='advisory':
  expected=item['gold_parameters'] or {};actual=p.get('parameters') or {}
  differences={k:{'gold':expected.get(k),'prediction':actual.get(k)} for k in sorted(set(expected)|set(actual)) if expected.get(k)!=actual.get(k)}
  reasons.append('严格规范键差异：'+json.dumps(differences,ensure_ascii=False))
  if p.get('template')=='software' and any(isinstance(s.get('answer'),dict) and any('_' in str(x) or '-' in str(x) for x in (s['answer'].get('parameters') or {}).get('commands',[])) for s in samples):
   reasons.append('软件名按 bundle 的首个字母数字 token 归一化；含下划线或连字符的命令可能被截短，原始与归一化参数均保留。')
 if row['executable_wrong']:reasons.append('执行判定不一致；review 按未接受计分。')
 causes[cause]+=1
 details.append({**row,'primary_cause':cause,'evidence_reasons':reasons,'recorded_samples':samples,
                 'temporary_pending_label':row['id'] in run.PENDING,'review_status':item.get('review_status'),'review_note':item.get('review_note')})
base.save_json(out/'full_v2_errors_detailed.json',details)
base.write_csv(out/'full_v2_errors_detailed.csv',details)
lines=['# full_v2 全部错误与原始样本诊断','','按模板、执行判定、逐条规范键任一不一致列出；只读既有响应，没有新调用或参数调整。','',
       '主要原因计数：'+json.dumps(dict(causes),ensure_ascii=False),'']
for r in details:
 lines += [f"## {r['id']} · {r['method']} · {r['primary_cause']}",'',r['statement'],'','原文引用：'+r['quote'],'',
  '标准：'+json.dumps({'template':r['gold_template'],'parameters':r['gold_parameters']},ensure_ascii=False),'',
  '预测：'+json.dumps({'decision':r['predicted_decision'],'template':r['predicted_template'],'parameters':r['predicted_parameters']},ensure_ascii=False),'',
  '原因：'+'；'.join(r['evidence_reasons']),'']
 if r['temporary_pending_label']:lines += ['此条标准按用户要求暂采 Claude 建议，仍待用户决定。','']
 lines += ['| 样本 | 原始答案 | 归一化参数 | 类型问题 |','|---|---|---|---|']
 for s in r['recorded_samples']:
  cell=lambda v:json.dumps(v,ensure_ascii=False).replace('|','\\|').replace('\n',' ')
  lines.append('| '+str(s['sample'])+' | '+cell(s['answer'])+' | '+cell(s['normalised_parameters'])+' | '+cell(s['type_problems'])+' |')
 lines.append('')
(out/'FULL_V2_ERRORS_DETAILED.md').write_text('\n'.join(lines),encoding='utf-8')
base.save_json(out/'full_v2_diagnostics.json',{'error_items':len(details),'primary_causes':dict(causes),'all_answers_preserved':True,'new_model_calls':0})
# Suggestions to review development labels are separate from scores. The
# supplied reviewed JSON and its six user-specified provisional choices remain
# unchanged, and these notes never enter the independent annotation packet.
concerns={
20:'陈述是凸包计算的点坐标，是否为内存结构而非被试必需的 pial 文件，需按 product_present 定义核对。',
21:'陈述是平均皮层厚度估计；需核对它是否确实要求 SurfaceMetric.Thickness 文件，而非派生数值。',
33:'陈述描述三批处理脚本对 T1/T2 的处理，需与“方法自身处理描述按 advisory”的通用规则核对。',
38:'原文同时提到 MATLAB 和 Image Processing Toolbox，标准只保留 matlab；需明确工具箱是否应单独表达。模型归一化成 image 也不是可用命令名，不能视为标准已被推翻。',
40:'原文明确要求 MATLAB 与 Image Processing Toolbox；与软件模板可覆盖 toolbox 的定义存在表达范围问题。严格键分歧仍按原标准计错。',
}
notes=['# 开发集标签复核建议（未改 gold）','','这些是来源和通用规则之间需要人审的疑点，不是新的标准答案。六条用户指定暂定标签仍按原要求计分，独立集盲标注包不含本文件。','']
for item_id,note in concerns.items():
 item=by_id[item_id]
 notes += [f"## {item_id}",'',item['statement'],'','引用：'+item['quote'],'','现行标准：'+json.dumps({'template':item['gold_template'],'parameters':item['gold_parameters']},ensure_ascii=False),'',note,'']
(out/'annotation_review_notes_v2.md').write_text('\n'.join(notes),encoding='utf-8')
summary=json.loads((out/'summary.json').read_text());failures=[]
for arm in run.ARMS:
 ps=json.loads((out/f'predictions_{arm}.json').read_text())
 for p in ps:
  if p['decision'] in {'provider_error','inference_error'}:failures.append({'arm':arm,'item':by_id[p['id']],'prediction':p})
base.save_json(out/'provider_and_structure_failures.json',failures)
# A combined attempt table includes source-card extraction and makes the 1200
# round-wide ceiling independently checkable without publishing raw responses.
combined=[]
for phase,folder in [('development',out),('independent_card_extraction',independent)]:
 es=[json.loads(x) for x in (folder/'requests/calls.jsonl').read_text().splitlines()];end={e['request_id']:e for e in es if e['event']=='end'}
 for e in es:
  if e['event']!='start':continue
  last=end.get(e['request_id'],{})
  combined.append({'phase':phase,**{k:(e if k in e else last).get(k) for k in ['ordinal','arm','item_id','sample','attempt','request_id','status','http_status','finish_reason','input_tokens','output_tokens','total_tokens','reasoning_content_present','reasoning_tokens']}})
base.write_csv(out/'all_call_usage.csv',combined)
audit=json.loads((out/'audit.json').read_text());quote=json.loads((independent/'quote_verification.json').read_text())
extra=['','## 完整运行核验','',
 '合入提交：79d6bcb（审核版标签）和 765bae2（v2 算法）。运行器与源卡工具提交 df94959；源码与盲标注材料已通过完整默认后端测试：894 passed、14 skipped、59 subtests passed，144 条既有警告。','',
 '评分口径：模板准确率采用最佳提案（包括 review）；可执行正类仅 accepted 且非 advisory。review/拒绝/错误按未接受计入负类，因此负类不等于显式 advisory。规范键按 (method, template, parameters) 去重，严格匹配，不补做同义词映射。','',
 '累计 HTTP 请求（含重试/补采/源卡抽取）：'+str(audit['total_http_attempts'])+'/1200；开发集 '+str(audit['development_http_attempts'])+'，源卡抽取 '+str(audit['independent_card_extraction_http_attempts'])+'。','',
 '已知 token：输入 '+str(audit['known_input_tokens'])+'，输出 '+str(audit['known_output_tokens'])+'，合计 '+str(audit['known_total_tokens'])+'；完整 usage 未知 '+str(audit['unknown_usage_requests'])+' 次，未当作零计账。','',
 '实际返回：严格 JSON 对象 '+str(audit['strict_json_object_responses'])+' 条，空文本 '+str(audit['empty_text_responses'])+' 条，其他非对象/无效 JSON '+str(audit['non_object_or_invalid_json_responses'])+' 条；非 length 的空文本未补采。length '+str(audit['length_responses'])+' 次；报告推理 token 大于零 '+str(audit['reasoning_tokens_positive_responses'])+' 次、带非空 reasoning_content '+str(audit['reasoning_content_present_responses'])+' 次。因此关闭思考是请求设置，网关没有在所有响应上一致遵守；8192 上限和实际 finish_reason 已逐次记录。 严格 JSON 统计按完整 content 解析；算法沿用 bundle 从文本中提取对象的解析器，非严格 JSON 不直接等于算法解析失败。','',
 '环境/输出结构失败共 '+str(len(failures))+' 个组别条目，见 provider_and_structure_failures.json。完整 full_v2 错误见 FULL_V2_ERRORS_DETAILED.md；开发标签复核建议另列 annotation_review_notes_v2.md，未改 gold 或分数。','',
 '开发集原计划 756 个采样槽位；实际启动 '+str(len({e['logical_id'] for e in ev if e['event']=='start' and isinstance(e.get('sample'),int)}))+' 个；截断补采 '+str(sum(summary[a]['truncation_replacements'] for a in run.ARMS))+' 次。full_v2 的 8 条接口失败提前终止了后续共 16 个槽位，未重新采样替换它们。','',
 '为减轻早期限流，仅调整传输发包节奏；调整前 124 次请求全部有结束记录，18 条已完成预测及所有已有响应保持原样。freeze_history 记录旧/新摘要、账本前缀和预测摘要。算法文件与 bundle 完全相同，没有逐项调参或答案修补。','',
 'v1 与 v2 还存在思考/长度/JSON 调用设置差异；这里报告开发比较，不把改进单独归因于某一项修正。','',
 '## 独立测试候选集与 Claude 标注交接','',
 '| 方法 | 全卡陈述 | 待标注陈述 |','|---|---:|---:|']
for m in quote['methods']:extra.append(f"| {m['method']} | {m['card_statements']} | {m['annotation_statements']} |")
extra += ['', '96 条引用与来源文本的精确位置均已核验，32 条补足引用或收窄语义范围，原卡与逐项修改记录保留。按与开发集相同的 inputs/conditions/checks/exceptions 字段取 45 条；方法与来源 URL 均不复用，精确规范化陈述/引文重复已检查。','',
 'Workbench 原请求 -surface-area 以官方命令 -surface-vertex-areas 记录。旧开发集已使用的 NMT 总览页被排除，采用未用过的官方 CHARM 与 Install_NMT 文档。','',
 'Claude 盲标注包含原文、陈述、空白表和通用规范，不含算法预测、分数或开发集标签。本环境没有可用 Claude 工具/CLI，交接包供转交，未声称已获得 Claude 标注。仅冻结源卡/交接文件，尚未生成或冻结独立测试 gold。后续收到标注冻结通知后再运行 full_v2/k1_v2/direct_v2/retrieval_only。','',
 '## 确认事项','',
 '没有输出密钥；没有部署、重启已有服务、访问/处理保留组、提交预处理、发起真实分析或覆盖知识层手写条件。独立集算法评测调用为 0。','']
with (out/'REPORT.md').open('a',encoding='utf-8') as f:f.write('\n'.join(extra))
(out/'audit_scripts').mkdir(exist_ok=True)
(out/'audit_scripts/build_diagnostics.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({'full_v2_error_items':len(details),'causes':dict(causes),'combined_request_rows':len(combined)},ensure_ascii=False))
