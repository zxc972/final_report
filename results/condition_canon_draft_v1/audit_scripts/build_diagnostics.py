
"""Derive per-attempt usage and statement diagnostics without additional calls."""
from pathlib import Path
import json,csv,importlib.util,collections
ROOT=Path('/data/xuancheng/agent_v1/round16_source');OUT=ROOT/'results/condition_canon_draft_v1'
spec=importlib.util.spec_from_file_location('diag_canon',ROOT/'agent/modules/agent/backend/analysis_condition_canonicalizer.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
def read(p):return json.loads(p.read_text())
gold=read(ROOT/'evaluation/condition_gold/gold_draft_v1.json')
es=[json.loads(x) for x in (OUT/'requests/calls.jsonl').read_text().splitlines()]
starts=[e for e in es if e['event']=='start'];ends={e['request_id']:e for e in es if e['event']=='end'}
columns=['ordinal','phase','arm','item_id','sample','attempt','logical_id','model','observed_model','http_status','status','finish_reason','input_tokens','output_tokens','total_tokens','usage_known','prompt_sha256']
with (OUT/'call_usage.csv').open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
 for s in sorted(starts,key=lambda e:e['ordinal']):
  end=ends.get(s['request_id'],{});row={k:s.get(k) for k in columns};row['phase']=s.get('phase','primary');row.update({k:end.get(k) for k in ['observed_model','http_status','finish_reason','input_tokens','output_tokens','total_tokens']});row['status']=end.get('status','unfinished');row['usage_known']=all(end.get(k) is not None for k in ['input_tokens','output_tokens','total_tokens']);writer.writerow(row)
preds=read(OUT/'predictions_full.json');errors=read(OUT/'full_errors.json');by_error={e['id']:e for e in errors};diagnostics=[]
for item,pred in zip(gold['items'],preds):
 ranked=c.Retriever().rank(item['statement']+' '+item['quote']);samples=[]
 for sample in range(1,6):
  logical=f"full:{item['id']}:{sample}";attempts=[s for s in starts if s['logical_id']==logical]
  records=[ends[s['request_id']] for s in attempts if s['request_id'] in ends]
  usable=[e for e in records if e.get('status')=='ok' or e.get('status')=='invalid_response' and e.get('finish_reason')=='length']
  if not usable:samples.append({'sample':sample,'result':'no_response','http_attempts':len(attempts)});continue
  response=usable[-1];text=response.get('text','');answer=None;problems=[]
  try:
   answer=c.parse_answer(text)
   if answer:problems=c.type_check(answer[0],answer[1],gold['slots'])
  except (ValueError,TypeError,KeyError,AttributeError) as e:problems=[type(e).__name__]
  state='valid' if answer and not problems else 'type_invalid' if answer else 'empty_answer' if not text else 'none_or_unparseable'
  samples.append({'sample':sample,'result':state,'http_attempts':len(attempts),'finish_reason':response.get('finish_reason'),'output_tokens':response.get('output_tokens'),'template':answer[0] if answer else None,'parameters':answer[1] if answer else None,'type_problems':problems})
 diag={'id':item['id'],'method':item['method'],'gold_template':item['gold_template'],'gold_template_in_top3':item['gold_template'] in [n for n,_ in ranked],'retrieved':ranked,'decision':pred['decision'],'samples':samples,'sample_result_counts':dict(collections.Counter(x['result'] for x in samples))}
 diagnostics.append(diag)
 if item['id'] in by_error:
  row=by_error[item['id']];row['sample_diagnostics']=diag
  length=sum(x.get('finish_reason')=='length' for x in samples)
  if length:row['reasons'].append(f'{length}/5 次样本因 2048 token 上限结束，可能未给出完整 JSON；保持原回答，未重采样')
  invalid=[p for sample in samples for p in sample.get('type_problems',[])]
  if invalid:row['reasons'].append('类型检查问题：'+'；'.join(sorted(set(invalid))))
  if pred.get('decision')=='provider_error':row['failure_category']='provider_environment'
  elif row['template_wrong']:row['failure_category']='template_mismatch'
  elif row['executable_wrong']:row['failure_category']='decision_not_accepted'
  else:row['failure_category']='parameter_key_mismatch'
(OUT/'full_diagnostics.json').write_text(json.dumps(diagnostics,ensure_ascii=False,indent=2)+'\n')
(OUT/'full_errors_detailed.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2)+'\n')
fields=['id','method','field','statement','gold_template','gold_parameters','predicted_decision','predicted_template','predicted_parameters','failure_category','reasons']
with (OUT/'full_errors_detailed.csv').open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
 for row in errors:writer.writerow({k:json.dumps(row.get(k),ensure_ascii=False) if isinstance(row.get(k),(dict,list)) else row.get(k) for k in fields})
lines=['# Full 组逐条错误与调用诊断','','以下标准答案均为未审核草稿。任何模板、可执行判定或逐条规范键不一致均列入；接口失败另列类别。','']
for row in errors:
 lines += [f"## {row['id']} · {row['method']}",'',row['statement'],'','草稿标准：`'+json.dumps({'template':row['gold_template'],'parameters':row['gold_parameters']},ensure_ascii=False)+'`','','预测：`'+json.dumps({'decision':row['predicted_decision'],'template':row['predicted_template'],'parameters':row['predicted_parameters']},ensure_ascii=False)+'`','','原因：'+'；'.join(row['reasons']),'']
(OUT/'FULL_ERRORS_DETAILED.md').write_text('\n'.join(lines))
status=read(OUT/'run_status.json');usage=read(OUT/'usage.json')
all_ends=list(ends.values());length=sum(e.get('finish_reason')=='length' for e in all_ends)
note=['','## 调用与运行限制','',f"全部 HTTP 请求 {usage['http_attempts']} 次；已知 token {usage['total_tokens']}（输入 {usage['input_tokens']}、输出 {usage['output_tokens']}）；{usage['unknown_usage_requests']} 次请求缺少完整 usage，不能将已知合计视为精确账单总量。",'',f"收到 {length} 条 finish_reason=length 响应；长度上限为调用前固定的 2048 token。这些空回答保留为未给出有效答案，没有重采样替换。接口/预算失败 {status.get('provider_failure_items',0)} 个组别-条目，详见 provider_failures.json。",'','用户随后明确授权 1000 次累计请求上限；独立冻结的补跑阶段只完成因原 800 次上限遗漏、且没有收到模型回答的条目。所有已有回答与空回答保持原样。两次运行器修复仅涉及 null 长度耗尽兼容、传输退避、取消排队和接口失败隔离。原冻结、调用账本前缀和已完成预测均保留于 freeze_history。算法、提示、标签、来源和 τ/δ/K 等默认参数始终未变。','','逐条原因及 5 次样本诊断见 FULL_ERRORS_DETAILED.md / full_errors_detailed.csv / full_diagnostics.json；每次请求的 token 见 call_usage.csv。原始 HTTP 调用记录只保留在开发主机和本地交付，不推送公开源码分支。','']
with (OUT/'REPORT.md').open('a') as f:f.write('\n'.join(note))
print(json.dumps({'full_error_items':len(errors),'error_categories':dict(collections.Counter(e['failure_category'] for e in errors)),'length_limited_responses':length,'call_usage_rows':len(starts)},ensure_ascii=False))
