from pathlib import Path
import json,sys,subprocess,hashlib,os,socket
D=Path('/data/xuancheng/agent_round11_trial_20261022');B=D/'backend_review';F=D/'frontend_review'
assert all(v==0 for v in json.loads((D/'audit/preflight_tests.json').read_text()).values())
assert json.loads((D/'stage0/offline_ready.json').read_text())['passed']
for repo in [B,F]:assert not subprocess.check_output(['git','-C',str(repo),'status','--porcelain']).strip()
assert (B/'knowledge_analysis/experiment_budget.json').read_bytes()==(D/'experiment_budget.json').read_bytes()
for pid,ticks in [(4023131,'266334328'),(4008469,'265114375'),(4008476,'265114396')]:
    assert (Path('/proc')/str(pid)/'stat').read_text().split(') ',1)[1].split()[19]==ticks
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('ops_manifest',B/'backend/analysis_operations.py');m=module_from_spec(spec);spec.loader.exec_module(m)
manifest=m.operations_manifest()
sealed=json.loads((D/'stage0/offline_P1_commit.json').read_text())
assert sealed['execution_bundle']['operations']['library']['sha256']==manifest['sha256']
# Retain original private hull reference and original unchanged contract.
for hemi,item in json.loads((D/'private_reference/hull_reference.json').read_text()).items():
    assert hashlib.sha256((Path('/data/xuancheng/featurize_20261011/data/KM002/KM002/surf')/(hemi+'.pial')).read_bytes()).hexdigest()==item['input_sha256']
sys.path.insert(0,str(D))
import dev_server as server
model=server.audited_factory(model=server.MODEL,base_url=server.BASE,api_key=server.SECRET)
checks={'sync_http_identity':model.http_client is server.SHARED_HTTP,'async_http_identity':model.http_async_client is server.SHARED_ASYNC_HTTP,'sdk_sync_root_identity':model.root_client._client is server.SHARED_HTTP,'sdk_async_root_identity':model.root_async_client._client is server.SHARED_ASYNC_HTTP,'provider_requests':json.loads((D/'provider_budget.json').read_text())['http_started']}
assert all(checks[k] for k in checks if k!='provider_requests') and checks['provider_requests']==0
(D/'audit/sdk_client_wiring.json').write_text(json.dumps(checks,indent=2))
server.check_protection()
for port in [8127,18774]:
    with socket.socket() as sock:sock.bind(('127.0.0.1',port))
record={'backend_head':subprocess.check_output(['git','-C',str(B),'rev-parse','HEAD'],text=True).strip(),'frontend_head':subprocess.check_output(['git','-C',str(F),'rev-parse','HEAD'],text=True).strip(),'operations':{k:v for k,v in manifest.items() if k!='functions'},'source_hashes':{str(p.relative_to(B)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['backend','knowledge_analysis','experiments/round11'] for p in (B/folder).rglob('*') if p.is_file() and p.suffix in {'.py','.json','.sha256'}}}
(D/'audit/trial_source_freeze.json').write_text(json.dumps(record,indent=2))
py='/data/xuancheng/agent/modules/agent/.venv-coding/bin/python'
with (D/'dev_backend.log').open('ab') as log:
    process=subprocess.Popen([py,'-B',str(D/'dev_server.py')],cwd=B,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(D/'audit/dev_backend_process.json').write_text(json.dumps({'pid':process.pid,'port':8127,'cwd':str(B)},indent=2))
config=D/'vite.preview.config.ts'
config.write_text("import original from './frontend_review/vite.config.ts';\nexport default { ...original, root: '/data/xuancheng/agent_round11_trial_20261022/frontend_review', cacheDir: '/data/xuancheng/agent_round11_trial_20261022/vite_cache', server: { ...original.server, port: 18774, strictPort: true } };\n")
env=os.environ.copy();env.update(PATH='/data/xuancheng/agent/.refactor_tools/node-v22.14.0-linux-x64/bin:'+env['PATH'],AGENT_PORT='8127',VITE_AGENT_BACKEND_PORT='8127',VITE_AGENT_BACKEND_URL='http://127.0.0.1:18127',VITE_DEV_PORT='18774',VITE_DEV_HOST='127.0.0.1')
with (D/'dev_frontend.log').open('ab') as log:
    front=subprocess.Popen(['npm','run','dev','--','--config',str(config)],cwd=F,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(D/'audit/dev_frontend_process.json').write_text(json.dumps({'pid':front.pid,'port':18774,'cwd':str(F)},indent=2))
print(json.dumps({'ready':True,'sdk_requests':0,'backend_pid':process.pid,'frontend_pid':front.pid,'ops_sha256':manifest['sha256']}),flush=True)
