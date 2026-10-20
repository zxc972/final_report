"""Freeze source-level references independently from model NiBabel parsing."""
import pathlib,struct,hashlib,json,time,sys
R=pathlib.Path('/data/xuancheng/agent_overnight_20261020');O=R/'independent_references/sbm_sources_20261020';O.mkdir(exist_ok=False);roots={s:pathlib.Path('/data/xuancheng/human_fastsurfer/subjects')/s for s in ['100610','101309','101410']};out={}
for s,p in roots.items():
 for h in ['lh','rh']:
  sphere=p/'surf'/(h+'.sphere.reg');thick=p/'surf'/(h+'.thickness');label=p/'label'/(h+'.cortex.label')
  with sphere.open('rb')as f:
   assert int.from_bytes(f.read(3),'big')==16777214;f.readline();f.readline();nv,nf=struct.unpack('>2i',f.read(8));xyz=f.read(12*nv);assert len(xyz)==12*nv
  with thick.open('rb')as f:
   assert int.from_bytes(f.read(3),'big')==16777215;n,faces,nvalues=struct.unpack('>3i',f.read(12));assert n==nv and nvalues==1;vals=f.read(4*n);assert len(vals)==4*n
  ls=label.read_text().splitlines();assert ls[0].startswith('#');declared=int(ls[1]);ids=[int(x.split()[0])for x in ls[2:]if x.strip()];assert len(ids)==declared and len(set(ids))==declared and all(0<=v<nv for v in ids)
  stem=s+'_'+h;paths={}
  for name,raw in [('sphere_f32be_xyz.bin',xyz),('thickness_f32be.bin',vals),('cortex_vertices_u32be.bin',struct.pack('>'+str(len(ids))+'I',*ids))]:
   q=O/(stem+'_'+name);q.write_bytes(raw);paths[name]={'path':q.name,'sha256':hashlib.sha256(raw).hexdigest()}
  out[stem]={'subject':s,'hemisphere':h,'n_vertices':nv,'n_faces':nf,'n_cortex_vertices':declared,'source_sha256':{x.name:hashlib.sha256(x.read_bytes()).hexdigest()for x in [sphere,thick,label]},'reference_files':paths,'count_line_is_not_a_vertex_record':True,'count_value_happens_to_be_valid_cortex_vertex':declared in set(ids)}
(O/'source_reference.json').write_text(json.dumps({'created':time.time(),'reference_exposed_to_generation':False,'algorithm':'stdlib big-endian surface/curvature decoder, explicit two-line label header skip, count/uniqueness/range checked','subjects':out},indent=2))
print(json.dumps({k:{x:v[x]for x in ['n_vertices','n_cortex_vertices','count_value_happens_to_be_valid_cortex_vertex']}for k,v in out.items()},indent=2))
sys.path.insert(0,'/data/xuancheng/agent/modules/agent');from backend.analysis_executor import SandboxExecutor
W=R/'independent_references/sbm_public_ico_reference';W.mkdir(exist_ok=False);p=W/'copy_public_ico.py';p.write_text("import shutil,hashlib,json\nfrom pathlib import Path\np=Path('/opt/freesurfer-7.2.0/lib/bem/ic6.tri');shutil.copyfile(p,'/work/ic6.tri');print(json.dumps({'source':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}))\n")
result=SandboxExecutor(W,[]).run(p,timeout_seconds=40);assert result['status']=='success',result;(W/'reference_copy_receipt.json').write_text(json.dumps(result,indent=2));print(json.dumps({'public_ico_copy_status':result['status'],'public_ico_metadata':result['stdout']},indent=2))
