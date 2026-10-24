"""Host-only E1 path wiring fix. It never changes the frozen actor or numeric rules.
The native API returns output_directory relative to the user's output workspace.
Preserve original grading records and write host_grade_path_corrected.json.
"""
import hashlib,importlib.util,json,sys
from pathlib import Path
SOURCE=Path('/data/xuancheng/agent_v1/round24_source');BATCH=Path('/data/xuancheng/agent_v1/retests/round24_20261024');WORKSPACE=Path('/data/xuancheng/agent_v1/workspaces/env-smoke/output')
src=(SOURCE/'agent/experiments/round24/host_verifier.py').read_text()
src=src.replace("REPO=Path(__file__).resolve().parents[3]",'REPO=SOURCE')
src=src.replace("p=Path(output)/filename;comp=", "p=resolve_output(metadata)/filename;comp=")
src=src.replace("folder/'host_grade.json'", "folder/'host_grade_path_corrected.json'")
# Every numerical reader, comparator, scope and tolerance comes from the frozen verifier unchanged.
def resolve_output(metadata,workspace=WORKSPACE):
 path=Path(metadata.get('output_directory') or '')
 if not metadata.get('output_directory'):raise ValueError('No native output path')
 path=(path if path.is_absolute() else workspace/path).resolve()
 if not path.is_relative_to(workspace.resolve()):raise ValueError('Output path escapes workspace')
 if path.name!=metadata.get('run_id'):raise ValueError('Output path must bind the native run ID')
 return path
if __name__=='__main__':
 sample=WORKSPACE/'.analysis_runs/fixture_owner/fixture_run'
 assert resolve_output({'output_directory':'.analysis_runs/fixture_owner/fixture_run','run_id':'fixture_run'})==sample
 assert resolve_output({'output_directory':str(sample),'run_id':'fixture_run'})==sample
 for bad in ({'output_directory':'../../outside/fixture_run','run_id':'fixture_run'},{'output_directory':str(sample),'run_id':'wrong_run'},{'run_id':'fixture_run'}):
  try:resolve_output(bad);raise AssertionError('Invalid output path accepted')
  except ValueError:pass
 namespace={'__name__':'e1_path_fix','__file__':str(SOURCE/'agent/experiments/round24/host_verifier.py'),'SOURCE':SOURCE,'resolve_output':resolve_output};exec(compile(src,'e1_original_verifier_with_path_resolution','exec'),namespace)
 cases=json.loads((BATCH/'authorization.json').read_text()).get('launched_cases',[])
 for case in cases:
  if (BATCH/('case_'+case)/'summary.json').exists():namespace['grade'](BATCH,case)
 (BATCH/'path_fix_audit.json').write_text(json.dumps({'reason':'Native output_directory is workspace-relative; original host verifier omitted the workspace prefix','original_actor_source_unchanged':True,'numeric_reference_comparator_tolerances_unchanged':True,'original_grading_records_preserved':True,'same_outputs_regraded_no_analysis_reruns':True,'model_calls':0,'valid_relative_absolute_fixtures':2,'rejected_path_or_identity_fixtures':3,'host_fix_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'regraded_cases':cases},indent=2)+'\n')
