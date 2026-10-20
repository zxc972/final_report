import pathlib,json,shutil,hashlib,time
R=pathlib.Path('/data/xuancheng/agent_overnight_20261020');P=pathlib.Path('/data/xuancheng/retrieval_pilot_20261020');D=R/'research_evidence_v1';assert not D.exists(),'Never overwrite an existing evidence release'
D.mkdir();shutil.copytree(P/'round2'/'index',D/'index');shutil.copytree(R/'domain_graph'/'sources',D/'sources');shutil.copyfile(R/'domain_graph'/'graph.json',D/'domain_graph.json');shutil.copyfile(R/'research_retrieval_worker.py',D/'worker.py')
corpus=json.loads((P/'round2'/'expanded_corpus.json').read_text());docs=[]
for row in corpus:
 q=dict(row);q['text_sha256']=hashlib.sha256(q['text'].encode()).hexdigest();q.setdefault('source_scope','Registered paragraph/excerpt from previous LightRAG experiment, not a full paper');docs.append(q)
manifest=json.loads((R/'domain_graph'/'source_manifest.json').read_text());M=R/'volume_method_context';vm=json.loads((M/'provenance.json').read_text())
for name in ['fastsurfer_v254_segstats','fastsurfer_v254_lut']:
 x=next(x for x in vm if x['id']==name);x['prior_fetch_attempt']={k:x[k] for k in ['status','error','error_type'] if k in x};raw=(M/(name+'.txt')).read_bytes();source=next(t for t in manifest if t['id']==name);assert hashlib.sha256(raw).hexdigest()==source['sha256'];x.update(status='downloaded_local_relay',source_version='v2.5.4',raw_sha256=source['sha256'],text_file=name+'.txt',text_sha256=source['sha256'],bytes=len(raw),relay_note='Downloaded from author URL on workstation after server timeout; bytes verified after SCP; failed attempt retained')
(M/'provenance.json').write_text(json.dumps(vm,ensure_ascii=False,indent=2))
for x in vm:
 if x.get('status') not in ['downloaded','downloaded_local_relay']:continue
 path=M/x['text_file'];text=path.read_text();docs.append({'id':'OFFICIAL_'+x['id'],'url':x['url'],'heading':x['id'],'source_scope':'Official snapshot '+x['source_version']+'; installed compatibility and sample applicability must be checked','text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
for x in manifest:
 if x.get('plain_text_path'):
  text=(R/'domain_graph'/'sources'/x['plain_text_path']).read_text();docs.append({'id':'ATLAS_'+x['id'],'url':x['url'],'heading':x['id'],'source_scope':'Official macaque atlas documentation snapshot; no current sample registration established','text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()})
assert len({d['id'] for d in docs})==len(docs)
(D/'documents.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2))
files={str(p.relative_to(D)):hashlib.sha256(p.read_bytes()).hexdigest() for p in D.rglob('*') if p.is_file() and not p.is_symlink()}
cfg={'schema':'primatex.research_retrieval.v1','python':str(P/'.venv'/'bin'/'python'),'worker_sha256':files['worker.py'],'documents_sha256':files['documents.json'],'domain_graph_sha256':files['domain_graph.json'],'embedding':'BAAI/bge-small-en-v1.5 fixed local verified ONNX, 384 dimensions','native_graph':'frozen previous LightRAG round2; new official parents are lexical overlay until separate indexed extraction','api_calls_per_retrieval':0,'sources':len(docs),'created':time.time(),'snapshot_files':files}
(D/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2))
print(json.dumps({'root':str(D),'registered_sources':len(docs),'snapshot_files':len(files),'native_index_untouched':True,'remote_provider_called':False},indent=2))
