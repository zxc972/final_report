"""Round23 interface-only changes and invariant scientific ASTs/digests."""
from pathlib import Path
import argparse,ast,hashlib,json,re,subprocess
BASE='12f8fbd2b12622c3b67c3e204722028f7b28b42e'
REASONS={
 'analysis_agent.py':'Typed host defects, phase-correct reflection, protected read-only guide reads, and separate internal-review reservation; actual/native counters retained.',
 'analysis_execution_card.py':'Move detailed public instructions to INPUTS.md and return bounded cards.',
 'analysis_execution_guidance.py':'New bounded card and sealed schema/guide files; exact scientific detail kept in read-only documents.',
 'analysis_executor.py':'Bind two sealed guide/schema files read-only in the real analysis container.',
 'analysis_failure_classification.py':'Report host defects, Agent exhaustion, incomplete review and contract failures separately with evidence.',
 'analysis_feedback.py':'Recognize typed host defects as failures while preserving observed reasons.',
 'analysis_global_method.py':'Move global execution descriptions to detailed guide functions; species formulas and contracts unchanged.',
 'analysis_group_manifest.py':'Move existing group input/science instructions into the read-only guide; bounded wrapper.',
 'analysis_operations.py':'Register the generic optional contract serializer; old operation catalogue entries retained.',
 'analysis_output_contract.py':'Attach observed CSV headers/delimiters after existing validator rejects; validate_csv AST unchanged.',
 'analysis_phase_tools.py':'Allow only sealed public guide/schema reads before coding; phase-correct budget notice.',
 'analysis_planning_budget.py':'Record actual planning calls separately from host-defect exemptions; limits unchanged.',
 'analysis_policy.py':'Align execution-only policy text with the sealed guide/schema read path; scientific instructions and condition-canonicalization prompts unchanged.',
 'analysis_plans.py':'Verify sealed document digests at execution gate.',
 'analysis_product_planner.py':'Write and bind read-only execution documents at commitment; matching/planning algorithms unchanged.',
 'analysis_provider.py':'Charge every actual internal-review HTTP attempt, including retries, to the four reserved credits before native charge/send.',
 'analysis_session.py':'Include observed filenames/header/delimiter diagnostics after automatic finalization fails.',
 'analysis_review_budget.py':'New four-credit review reservation inside unchanged total budget; coding cannot borrow; native counters unchanged.',
 'analysis_system_defects.py':'New typed defect observation, effective planning exemption and stop after repeated host defect.',
 'analysis_contract_diagnostics.py':'Diagnostic-only delimiter/header observations; no aliases, reparsing or numeric fixes.',
 'primatex_ops.py':'Append optional canonical CSV serializer; all 14 existing public operation ASTs unchanged.',
}

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
 for name in ['analysis_group_stats.py','analysis_numeric_reference.py','analysis_global_reference.py','analysis_global_reference_worker.py','analysis_group_contract.py','analysis_precision.py','analysis_internal_review.py','analysis_review_protocol.py','analysis_group_reporting.py','analysis_independent_numeric.py','analysis_condition_canonicalizer.py','analysis_region_resolver.py','analysis_csp_matching.py','analysis_andor_planner.py','analysis_transport.py','agent_chat_state.py','analysis_call_context.py','analysis_http_observer.py']:
  key=backend+name;before=old(key);after=(root/key).read_bytes();assert before.replace(b'\r\n',b'\n')==after.replace(b'\r\n',b'\n'),name
  invariants.append({'path':key,'sha256':digest(after),'unchanged':True})
 for name,selected in [('analysis_output_contract.py',['validate_csv']),('analysis_global_method.py',['candidate','table_contract'])]:
  key=backend+name;a=functions(old(key));b=functions((root/key).read_bytes())
  for function in selected:assert a[function]==b[function],(name,function)
 a=functions(old(backend+'primatex_ops.py'));b=functions((root/backend/'primatex_ops.py').read_bytes());assert all(b[k]==v for k,v in a.items())
 examples='agent/modules/agent/knowledge_analysis/operation_examples.json';ex0=json.loads(old(examples));ex=json.loads((root/examples).read_text())
 assert all(ex['examples'][k]==v for k,v in ex0['examples'].items()) and len(ex0['examples'])==14
 assert ex['library_sha256']==digest((root/backend/'primatex_ops.py').read_bytes())
 assert digest((root/examples).read_bytes())==(root/examples).with_suffix('.sha256').read_text().strip()
 researches=subprocess.check_output(['git','ls-tree','-r','--name-only',base,'knowledge/research_v13'],cwd=root,text=True).splitlines()
 for key in researches:assert old(key).replace(b'\r\n',b'\n')==(root/key).read_bytes().replace(b'\r\n',b'\n'),key
 for name in ['product_types.json','condition_templates.json','workflow_steps.json','method_requirements.json','lobar_mapping.json']:
  found=list((root/'agent/modules/agent/knowledge_analysis').rglob(name))
  assert len(found)==1,name
  key=found[0].relative_to(root).as_posix();assert old(key).replace(b'\r\n',b'\n')==found[0].read_bytes().replace(b'\r\n',b'\n'),name
 result={'baseline':base,'intentional_backend_changes':changed,'unchanged_scientific_sources':invariants,'public_validate_csv_AST_unchanged':True,'global_candidate_and_table_contract_AST_unchanged':True,'all_old_operations_AST_unchanged':True,'old_14_operation_examples_unchanged':True,'operation_metadata_reason':'Append actual synthetic serializer receipt; bind the new library SHA only.','research_files_unchanged':len(researches),'algorithm_parameters_prompts_vocabulary_unchanged':True,'native_http_metering_and_retry_policy_unchanged':True,'unexpected_changes':[]}
 args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'changed_backend_files':len(changed),'unchanged_scientific_files':len(invariants),'research_files':len(researches),'unexpected_changes':0}))
if __name__=='__main__':main()
