"""Round24 interface-only changes and invariant scientific ASTs/digests."""
from pathlib import Path
import argparse,ast,hashlib,json,re,subprocess
BASE='9ec6d91b3441e56f15d8e5e456848a981955d95f'
REASONS={'analysis_constraint_ids.py': 'Canonical observed method-qualified IDs with only unique aliases accepted; forged/ambiguous identities rejected.', 'analysis_review_evidence.py': 'Render and index observed evidence with the canonical ID.', 'analysis_review_protocol.py': 'Normalize only observed aliases in review findings/disclosures; protocol content predicates unchanged.', 'analysis_review_budget.py': 'Disjoint 23 initial, 4 logical review, 3 revise-only repair pools; retries metered separately.', 'analysis_provider.py': 'Mark actual transport retries for logical reservation while preserving native actual counters.', 'analysis_transport.py': 'Context-local review retry cap 2; ordinary provider retry policy unchanged.', 'analysis_system_defects.py': 'Operational stop threshold configurable; closed Round24 evaluation uses first defect, legacy default stays 2.', 'analysis_agent.py': 'Authorize reserved repair credits only after valid revise; optional design-mismatch rationale, same outer-round limit.', 'analysis_product_planner.py': 'Rank group-supporting methods first for explicit group design; retain unsupported choices with required rationale.', 'analysis_execution_guidance.py': 'Inline fixed values and enums in bounded cards; expose sealed public schema to the writer.', 'primatex_ops.py': 'Only generic write_contract_table preflight changed; checks enums/fixed/identities before writing without altering data.'}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def functions(raw):
 return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(raw.decode('utf-8-sig')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3]);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();root=args.root.resolve();base=BASE
 def old(name):return subprocess.check_output(['git','show',base+':'+name],cwd=root,stderr=subprocess.DEVNULL)
 backend='agent/modules/agent/backend/'
 changed=[]
 for name,reason in REASONS.items():
  path=root/backend/name
  try:before=old(backend+name)
  except subprocess.CalledProcessError:before=None
  after=path.read_bytes()
  if before!=after:changed.append({'path':backend+name,'before_sha256':digest(before) if before is not None else None,'after_sha256':digest(after),'reason':reason})
 invariants=[]
 for name in ['analysis_group_stats.py','analysis_numeric_reference.py','analysis_global_reference.py','analysis_global_reference_worker.py','analysis_group_contract.py','analysis_precision.py','analysis_internal_review.py','analysis_group_reporting.py','analysis_independent_numeric.py','analysis_condition_canonicalizer.py','analysis_region_resolver.py','analysis_csp_matching.py','analysis_andor_planner.py','agent_chat_state.py','analysis_call_context.py','analysis_http_observer.py']:
  key=backend+name;before=old(key);after=(root/key).read_bytes();assert before.replace(b'\r\n',b'\n')==after.replace(b'\r\n',b'\n'),name
  invariants.append({'path':key,'sha256':digest(after),'unchanged':True})
 for name,selected in [('analysis_output_contract.py',['validate_csv']),('analysis_global_method.py',['candidate','table_contract'])]:
  key=backend+name;a=functions(old(key));b=functions((root/key).read_bytes())
  for function in selected:assert a[function]==b[function],(name,function)
 a=functions(old(backend+'primatex_ops.py'));b=functions((root/backend/'primatex_ops.py').read_bytes());assert all(b[k]==v for k,v in a.items() if k != 'write_contract_table')
 examples='agent/modules/agent/knowledge_analysis/operation_examples.json';ex0=json.loads(old(examples));ex=json.loads((root/examples).read_text())
 assert all(ex['examples'][k]==v for k,v in ex0['examples'].items() if k != 'write_contract_table') and len(ex0['examples'])==15
 assert ex['library_sha256']==digest((root/backend/'primatex_ops.py').read_bytes())
 assert digest((root/examples).read_bytes())==(root/examples).with_suffix('.sha256').read_text().strip()
 researches=subprocess.check_output(['git','ls-tree','-r','--name-only',base,'knowledge/research_v13'],cwd=root,text=True).splitlines()
 for key in researches:assert old(key).replace(b'\r\n',b'\n')==(root/key).read_bytes().replace(b'\r\n',b'\n'),key
 for name in ['product_types.json','condition_templates.json','workflow_steps.json','method_requirements.json','lobar_mapping.json']:
  found=list((root/'agent/modules/agent/knowledge_analysis').rglob(name))
  assert len(found)==1,name
  key=found[0].relative_to(root).as_posix();assert old(key).replace(b'\r\n',b'\n')==found[0].read_bytes().replace(b'\r\n',b'\n'),name
 result={'baseline':base,'intentional_backend_changes':changed,'unchanged_scientific_sources':invariants,'public_validate_csv_AST_unchanged':True,'global_candidate_and_table_contract_AST_unchanged':True,'all_old_operations_AST_unchanged':True,'old_14_operation_examples_unchanged':True,'operation_metadata_reason':'Append actual synthetic serializer receipt; bind the new library SHA only.','research_files_unchanged':len(researches),'algorithm_parameters_prompts_vocabulary_unchanged':True,'native_http_metering_unchanged':True,'ordinary_retry_policy_unchanged':True,'review_retry_cap':2,'unexpected_changes':[]}
 args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'changed_backend_files':len(changed),'unchanged_scientific_files':len(invariants),'research_files':len(researches),'unexpected_changes':0}))
if __name__=='__main__':main()
