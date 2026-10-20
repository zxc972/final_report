from pathlib import Path
import subprocess,tarfile,io,json
REMOTE = r'''
from pathlib import Path
import os,stat,hashlib,json,datetime,re,sys,tarfile,io
R=Path('/data/xuancheng'); selected={}; skips=[]
SKIP={'node_modules','.venv','.venv-coding','venv','__pycache__','.git','.pytest_cache','.analysis_state','.analysis_service','.semantic_backups','.refactor_backups','.refactor_test_20261015','.refactor_tools','dist','build','.next','models','template','logs','runs','workspace','workspaces','http','cache','completion_cache','independent_references'}
EXT={'.py','.sh','.md','.txt','.json','.toml','.yaml','.yml','.tsx','.ts','.js','.jsx','.mjs','.cjs','.html','.css','.scss','.svg','.lock','.cfg','.ini','.cff','.graphml'}
NAMES={'LICENSE','NOTICE','NIPYPE_LICENSE','.gitignore','.gitmodules','.gitkeep','.prettierrc','primx','help'}
PATTERNS=[re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),re.compile(rb'\bsk-[A-Za-z0-9_-]{24,}\b'),re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b')]
def add(s,d):
 p=R/s
 if not p.is_file() or p.is_symlink(): skips.append({'source':s,'reason':'missing_or_nonregular'});return
 if p.name=='.env' or (p.name.startswith('.env.') and p.name!='.env.example'): skips.append({'source':s,'reason':'secret_environment_file'});return
 before=p.stat()
 if before.st_size>20*1024*1024:skips.append({'source':s,'reason':'large_file'});return
 data=p.read_bytes();after=p.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError('Concurrent edit: '+s)
 if any(x.search(data) for x in PATTERNS):raise RuntimeError('Potential secret, stopped: '+s)
 try:data.decode('utf-8-sig')
 except UnicodeDecodeError:skips.append({'source':s,'reason':'non_text_file'});return
 selected[d]=(s,data,stat.S_IMODE(before.st_mode),before.st_mtime)
def tree(s,d):
 for base,dirs,files in os.walk(R/s,followlinks=False):
  dirs[:]=sorted(x for x in dirs if x not in SKIP and not Path(base,x).is_symlink())
  for name in sorted(files):
   p=Path(base,name)
   if p.suffix.lower() in EXT or name in NAMES or name.startswith('MSM'):
    add(p.relative_to(R).as_posix(),d+'/'+p.relative_to(R/s).as_posix())
for name in ['README.md','LICENSE','NOTICE','CITATION.cff','.gitmodules','.gitignore']:add('agent/'+name,'agent/'+name)
for part in ['modules/agent','modules/gui','modules/neuro_pipeline','modules/primx_seg','workflows','docs']:tree('agent/'+part,'agent/'+part)
add('agent/modules/primx_seg/models/Readme.txt','agent/modules/primx_seg/models/Readme.txt')
W='agent_overnight_20261020'
for source,dest in [('research_evidence_v13','knowledge/research_v13'),('software_graph','knowledge/software_graph'),('domain_graph','knowledge/domain_graph_base')]:tree(W+'/'+source,dest)
for name in ['installed_requirements.txt','installed_api.json','model_provenance.json','embedding_audit.json']:add('retrieval_pilot_20261020/'+name,'environment/retrieval/'+name)
add('structural_env/README_zh.md','environment/structural_env_README_zh.md')
for part in ['recipes','manifests']:tree('structural_env/'+part,'environment/'+part)
for name in ['build_method_release_v12.py','curate_method_semantics_v13.py','extract_method_cards_v12.py','extract_comparative_method_cards_v12.py','collect_method_sources_v12.py','collect_comparative_sources_v12.py','collect_method_pdf_sources_urlencoded.py','build_research_evidence.py','build_research_v10_surface_volume.py','build_research_v11_mask_semantics.py','audit_graph_counts.py','audit_fresh_method_autonomy.py']:add(W+'/'+name,'tools/knowledge/'+name)
for name in ['source_manifest.json','pdf_source_manifest.json','additional_source_manifest.json','curvature_source_manifest.json','statistics_source_manifest.json','release_audit.json','semantic_quarantine.json','method_claim_quarantine.json','method_quote_transform_audit.json','semantic_correction_audit.json','fresh_task_freeze.json','internal_review_trial_freeze.json']:add(W+'/method_graph_loop_20261020/'+name,'knowledge/method_audit/'+name)
tree(W+'/method_graph_loop_20261020/extractions','knowledge/method_extractions')
for name in ['independent_nifti_pve.py','independent_surface_volume.py','independent_monkey_reference.py','independent_crossspecies_reference.py','independent_sbm_source_reference.py','independent_volume_reference.py','test_independent_nifti_pve.py','test_independent_surface_volume.py','review_fresh_monkey_numeric_v13.py','review_fresh_crossspecies_numeric_v13.py']:add(W+'/'+name,'evaluation/verifiers/'+name)
for p in sorted((R/W).glob('task_*.json')):add(p.relative_to(R).as_posix(),'evaluation/task_specs/'+p.name)
for name in ['task_index.json','分析类型与任务总表.md']:add('eval/'+name,'evaluation/'+name)
for name in ['comparison_metrics.json','contract_v2_review.json','graph_targeted_review.json','图文联合检索与原文检索_实测结果和Agent接入建议_20261020.md']:add('retrieval_pilot_20261020/'+name,'evaluation/retrieval/round1/'+name)
for name in ['comparison_metrics.json','frozen_questions.json','repair_review.json','final_status.json','第二轮跨步骤检索实测与修复结论_20261020.md']:add('retrieval_pilot_20261020/round2/'+name,'evaluation/retrieval/round2/'+name)
for name in ['first_run_retrieval.py','run_retrieval.py','export_graph.py']:add('retrieval_pilot_20261020/'+name,'tools/retrieval/'+name)
for name in ['run_expanded.py','retrieval_repair.py']:add('retrieval_pilot_20261020/round2/'+name,'tools/retrieval/round2/'+name)
for name in ['software_graph_count_audit.json','research_v11_count_audit.json','final_review_snapshot.json']:add(W+'/audit/'+name,'docs/evidence/'+name)
for d,(s,data,mode,mtime) in selected.items():
 if (R/s).read_bytes()!=data:raise RuntimeError('Concurrent source edit, retry: '+s)
records=[{'path':d,'source':str(R/s),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'mode':'100755' if mode&0o111 else '100644'} for d,(s,data,mode,mtime) in sorted(selected.items())]
manifest={'schema':'final_report.source_snapshot.v1','created_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'timezone':'Asia/Shanghai','visibility':'public','research_release':'research_evidence_v13','source_root':str(R),'source_unchanged_check':True,'source_files':len(records),'source_bytes':sum(x['bytes'] for x in records),'excluded_classes':['credentials and .env','FreeSurfer license','MRI and subject data','generated subject results and private numerical references','container images and model weights','virtual environments and node_modules','HTTP traces and run workspaces','PDF originals and duplicate historical releases'],'selection_skips':skips,'files':records}
m=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as t:
 for d,(s,data,mode,mtime) in sorted(selected.items()):
  i=tarfile.TarInfo(d);i.size=len(data);i.mode=mode;i.mtime=mtime;t.addfile(i,io.BytesIO(data))
 i=tarfile.TarInfo('SNAPSHOT_MANIFEST.json');i.size=len(m);i.mode=0o644;t.addfile(i,io.BytesIO(m))
'''
out=Path('final_report').resolve()
if out.exists():raise SystemExit('Destination exists; choose a new directory.')
r=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','xuancheng','python3','-'],input=REMOTE.encode(),capture_output=True,timeout=120)
if r.returncode:raise SystemExit(r.stderr.decode(errors='replace'))
t=tarfile.open(fileobj=io.BytesIO(r.stdout),mode='r:gz')
for m in t.getmembers():
 if not (out/m.name).resolve().is_relative_to(out) or not m.isfile():raise SystemExit('Unsafe member: '+m.name)
out.mkdir()
for m in t.getmembers():
 p=out/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read())
manifest=json.loads((out/'SNAPSHOT_MANIFEST.json').read_text(encoding='utf8'))
print(json.dumps({k:manifest[k] for k in ['created_at','source_files','source_bytes','selection_skips']},ensure_ascii=False,indent=2))