"""Review intentional interface changes without changing scientific references."""
from pathlib import Path
import ast
import hashlib
import json
import subprocess

ROOT=Path('/data/xuancheng/agent_v1/round21_source')
WORK=ROOT.parent/'round21_work'
BASE='a2189f3b3fc5dd05afac12fe9bd49e21a50c6b15'
REASONS={
'agent_chat_state.py':'Attach native HTTP charge identity to request-local context; reservation/retry/accounting rules unchanged.',
'analysis_agent.py':'Generic group-design tool documentation, actionable argument rejection before planner quota, and ToolMessage failure synchronization.',
'analysis_call_context.py':'Add a ContextVar carrying exact native HTTP attempt identity for the transport observer.',
'analysis_data_card.py':'Show dynamically observed registered metric names in compact multi-subject data cards.',
'analysis_feedback.py':'Recognize nested artifact/public-contract failure despite subprocess exit0 and retain bounded original failure reasons.',
'analysis_group_manifest.py':'Explain existing dict/list/key schema and expose raw-reading/keyed-BH interfaces; bind metric names from actual inputs.',
'analysis_independent_numeric.py':'Only new unassessed observation defaults become null; compare_rows/reference_rows, numerical rules and tolerances unchanged.',
'analysis_operations.py':'Register two additional public generic sandbox APIs and bind their actual synthetic examples.',
'analysis_overall_status.py':'Separate unassessed host differences from assessed public identity checks; final scientific verdict logic unchanged.',
'analysis_planning_tools.py':'Separate up-to-three pre-planner argument rejections from up-to-three actual planner entries; global budgets unchanged.',
'analysis_product_planner.py':'Accept explicit all-registered subject sentinel; original explicit-ID selection and scientific planning algorithms unchanged.',
'primatex_ops.py':'Append raw read-only group reader and identity-keyed BH; every pre-existing operation function AST unchanged.',
}
NEW={
'analysis_http_observer.py':'Install isolated-process httpx/httpx2 sync/async observers without changing retry/transport policy.',
'analysis_planning_arguments.py':'Validate registered IDs/metrics and required design fields using public data-card/profile metadata.',
}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def git_text(name):return subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT,stdin=subprocess.DEVNULL).decode('utf-8-sig')

def functions(text):return {n.name:ast.dump(n) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}


def main():
    before=json.loads((WORK/'protected_before.json').read_text())
    changed=[]
    for name,expected in before.items():
        path=ROOT/name
        if sha(path)!=expected:
            assert name.startswith('agent/modules/agent/backend/'),name
            assert path.name in REASONS,('unexpected protected file',name)
            changed.append({'path':name,'before_sha256':expected,'after_sha256':sha(path),'reason':REASONS[path.name]})
    assert {Path(r['path']).name for r in changed}==set(REASONS)
    for name in ['analysis_group_stats.py','analysis_numeric_reference.py','analysis_global_reference.py','analysis_global_reference_worker.py','analysis_group_contract.py','analysis_output_contract.py','analysis_precision.py','analysis_internal_review.py','analysis_review_protocol.py','analysis_group_reporting.py']:
        key='agent/modules/agent/backend/'+name
        assert sha(ROOT/key)==before[key],name
    ops_path='agent/modules/agent/backend/primatex_ops.py'
    old=functions(git_text(ops_path));new=functions((ROOT/ops_path).read_text())
    assert all(new[k]==value for k,value in old.items())
    path='agent/modules/agent/backend/analysis_independent_numeric.py'
    old=functions(git_text(path));new=functions((ROOT/path).read_text())
    assert all(old[k]==new[k] for k in ['compare_rows','reference_rows'])
    source=(ROOT/path).read_text();old_source=git_text(path)
    for const in ['ATOL','RTOL']:
        import re
        pattern=r'^'+const+r'\s*=.*$'
        matches=re.findall(pattern,source,re.M)
        assert matches and matches==re.findall(pattern,old_source,re.M)
    report={'baseline_commit':BASE,'baseline_protected_files':len(before),'intentional_changed':changed,
            'new_backend_files':[{'path':'agent/modules/agent/backend/'+name,'sha256':sha(ROOT/'agent/modules/agent/backend'/name),'reason':reason} for name,reason in NEW.items()],
            'research_v13_unchanged':True,'research_files':sum(name.startswith('knowledge/research_v13/') for name in before),
            'independent_reference_and_public_contract_files_unchanged':True,'original_ops_function_asts_unchanged':True,
            'numeric_comparison_and_reference_row_asts_unchanged':True,'ATOL_RTOL_unchanged':True,'unexpected_changes':[]}
    (WORK/'protected_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Round21 protected-file changes','', 'Baseline '+BASE+'. Each intentional change is an interface, observation or generic sandbox helper change.','', '| File | Reason |','|---|---|']
    for row in [*report['intentional_changed'],*report['new_backend_files']]:lines.append('| '+row['path']+' | '+row['reason']+' |')
    lines+=['','operation_examples.json and .sha256 are intentionally regenerated from actual synthetic calls to bind the extended library; original operation functions remain unchanged.','', 'All independent reference implementations, public scientific contract rules, tolerances, scientific review rules and 82 research_v13 files are unchanged.','']
    (ROOT/'agent/experiments/round21/PROTECTED_CHANGES.md').write_text('\n'.join(lines))
    print(json.dumps({'protected_files':len(before),'intentional_changed':len(changed),'new_backend_files':len(NEW),'unexpected_changes':0,'scientific_boundaries_unchanged':True}))

if __name__=='__main__':main()
