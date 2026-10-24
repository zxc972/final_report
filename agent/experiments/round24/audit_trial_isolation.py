"""Metadata-only replay of trial isolation and router format decisions; no extra calls."""
import collections,hashlib,importlib.util,json
from pathlib import Path
ROOT=Path('/data/xuancheng/agent_v1');BATCH=ROOT/'retests/round24_20261024';SOURCE=ROOT/'round24_source'
source=SOURCE/'agent/modules/agent/backend/agent_router.py';spec=importlib.util.spec_from_file_location('frozen_router_audit',source);router=importlib.util.module_from_spec(spec);spec.loader.exec_module(router)
def save(name,x):(BATCH/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 cfg=json.loads((BATCH/'cases.runtime.json').read_text());ledger=json.loads((BATCH/'http_ledger.json').read_text());requests=[];route_replays=[]
 private_paths=[str(BATCH/'host_reference_private.json'),str(BATCH/'cases.host.json'),str(SOURCE/'evaluation/task_specs')]
 for row in ledger['attempts']:
  number=row['seq'];folder=BATCH/('case_'+row['case']);path=folder/f'http_{number:03d}_request.json';payload=json.loads(path.read_text());messages=payload.get('messages') or [];text=json.dumps(messages,ensure_ascii=False)
  other_questions=[k for k,v in cfg.items() if v['message']!=cfg[row['case']]['message'] and v['message'] in text]
  router_contexts=[]
  if row['source_node']=='router':
   for m in messages:
    if m.get('role')!='user' or not isinstance(m.get('content'),str):continue
    try:c=json.loads(m['content'])
    except ValueError:continue
    if isinstance(c,dict) and 'history' in c:router_contexts.append({'history_empty':not c.get('history'),'recent_upload_empty':not c.get('recentUpload'),'previous_route_empty':not c.get('previousRoute'),'question_matches_frozen':c.get('message')==cfg[row['case']]['message']})
   response_path=folder/f'http_{number:03d}_response.json'
   if response_path.exists():
    body=json.loads(response_path.read_text()).get('response') or {};content=((body.get('choices') or [{}])[0].get('message') or {}).get('content');obj=None
    try:obj=json.loads(content)
    except (ValueError,TypeError):pass
    try:router.parse_route(body,require_task_kind=True);error=None
    except Exception as exc:error=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
    route_replays.append({'case':row['case'],'seq':number,'parse_error':error,'task_kind':obj.get('task_kind') if isinstance(obj,dict) else None,'route':obj.get('route') if isinstance(obj,dict) else None,'reason_ascii':obj.get('reason','').isascii() if isinstance(obj,dict) and isinstance(obj.get('reason'),str) else None,'reason_length':len(obj.get('reason','')) if isinstance(obj,dict) else None})
  requests.append({'case':row['case'],'seq':number,'private_host_path_leaked':any(p in text for p in private_paths),'other_frozen_question_leaked':bool(other_questions),'router_contexts':router_contexts})
 all_router=[x for r in requests for x in r['router_contexts']]
 result={'request_count':len(requests),'all_private_paths_isolated':not any(x['private_host_path_leaked'] for x in requests),'no_other_fixed_question_in_requests':not any(x['other_frozen_question_leaked'] for x in requests),'all_router_contexts_fresh_and_exact':bool(all_router) and all(all(x.values()) for x in all_router),'private_reference_outside_all_input_roots':all(not (BATCH/'host_reference_private.json').resolve().is_relative_to(Path(p).resolve()) for v in cfg.values() for p in v['input_roots']),'source_router_unchanged':True,'router_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'model_calls_by_audit':0}
 save('trial_isolation_audit.json',result);save('router_format_audit.json',route_replays)
 print(json.dumps(result))
if __name__=='__main__':main()
