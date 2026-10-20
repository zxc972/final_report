"""Source-derived software contract graph. Parses AST, never imports downloaded code."""
import ast,pathlib,json,urllib.request,hashlib,concurrent.futures,time,collections,re
R=pathlib.Path(__file__).parent;(R/'sources').mkdir(exist_ok=True)
def get(url):return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'PrimateX-method-reuse-study'}),timeout=35).read()
commit=json.loads(get('https://api.github.com/repos/nipy/nipype/commits/master'))['sha']
tree=json.loads(get(f'https://api.github.com/repos/nipy/nipype/git/trees/{commit}?recursive=1'))['tree']
families={'freesurfer','fsl','ants','spm','niftyreg','niftyseg','workbench','brainsuite'}
selected=[]
for row in tree:
 p=pathlib.PurePosixPath(row['path']);parts=p.parts
 if len(parts)==4 and parts[:2]==('nipype','interfaces') and parts[2] in families and p.suffix=='.py' and p.stem not in ['__init__','tests'] and not p.stem.startswith('test'):
  if parts[2]=='fsl' and p.stem not in ['base','preprocess','maths','utils','model']:continue
  if parts[2]=='spm' and p.stem not in ['base','preprocess','utils']:continue
  selected.append(str(p))
assert 10<=len(selected)<=80
manifest=[]
def fetch(path):
 url=f'https://raw.githubusercontent.com/nipy/nipype/{commit}/{path}';raw=get(url);dest=R/'sources'/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
 return {'path':path,'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'commit':commit}
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
 for future in concurrent.futures.as_completed([ex.submit(fetch,p) for p in selected]):
  try:manifest.append(future.result())
  except Exception as e:manifest.append({'error':type(e).__name__})
license_raw=get(f'https://raw.githubusercontent.com/nipy/nipype/{commit}/LICENSE');(R/'sources/NIPYPE_LICENSE').write_bytes(license_raw)
(R/'source_manifest.json').write_text(json.dumps({'repo':'https://github.com/nipy/nipype','commit':commit,'license_url':f'https://github.com/nipy/nipype/blob/{commit}/LICENSE','fetched_at':time.time(),'files':manifest},indent=2))
nodes={};edges={};quarantine=[]
def node(id,type,name,source=None,**props):
 n={'id':id,'type':type,'name':name,'review_status':'source_parsed_candidate','executable':False,**props}
 if source:n['source']=source
 nodes.setdefault(id,n);return id
def edge(a,p,b,source):
 if a not in nodes or b not in nodes:quarantine.append({'source':a,'relation':p,'target':b,'reason':'undeclared endpoint','evidence':source});return
 key=(a,p,b);edges.setdefault(key,{'source':a,'relation':p,'target':b,'evidence':source,'review_status':'source_parsed_candidate','executable':False})
def expr(x):
 try:return ast.literal_eval(x)
 except Exception:return {'expression':ast.unparse(x)}
root=node('software:nipype@'+commit,'SoftwareVersion','Nipype',commit=commit,underlying_software_versions='not_bound_to_installed_versions')
allclasses=[]
for m in manifest:
 if 'path' not in m:continue
 path=m['path'];text=(R/'sources'/path).read_text();lines=text.splitlines();family=path.split('/')[2];source={'url':m['url'],'sha256':m['sha256'],'path':path,'commit':commit}
 fileid=node('source:'+path,'SourceFile',path,source)
 familyid=node('software_family:'+family,'SoftwareFamily',family)
 edge(root,'HAS_INTERFACE_FAMILY',familyid,source)
 for c in ast.parse(text).body:
  if not isinstance(c,ast.ClassDef) or c.name.startswith('_'):continue
  # Pure fMRI, diffusion and first-level experiment interfaces are out of this seed's scope.
  if family=='fsl' and pathlib.PurePosixPath(path).stem=='preprocess' and not any(k in c.name.lower() for k in ['bet','fast','flirt','fnirt','applyxfm','applywarp','invwarp','convertwarp','convertxfm','robustfov']):continue
  if family=='fsl' and pathlib.PurePosixPath(path).stem=='model' and not any(k in c.name.lower() for k in ['randomise','glm','multiple','contrast']):continue
  if family=='spm' and not any(k in c.name.lower() for k in ['segment','normaliz','coreg','dartel','deform','warped','spmcommand','spminput']):continue
  if any(k in c.name.lower() for k in ['petpvc','mricorvol','fsf','slicetim','realign','fmri','eddy','topup','diffusion']):continue
  vals={}
  for v in c.body:
   if isinstance(v,ast.Assign) and len(v.targets)==1 and isinstance(v.targets[0],ast.Name):vals[v.targets[0].id]=v.value
  is_input='InputSpec' in c.name;is_output='OutputSpec' in c.name
  traits={k:v for k,v in vals.items() if not k.startswith('_') and isinstance(v,ast.Call) and k not in ['input_spec','output_spec']}
  is_interface='input_spec' in vals or '_cmd' in vals or '_command' in vals
  if not (is_input or is_output or is_interface):continue
  if c.name in ['TraitedSpec','CommandLineInputSpec']:continue
  cs={**source,'line_start':c.lineno,'line_end':c.end_lineno}
  cid=node('symbol:'+path+':'+c.name,'InputSpec' if is_input else 'OutputSpec' if is_output else 'SoftwareInterface',c.name,cs,family=family,description=ast.get_docstring(c),bases=[ast.unparse(b) for b in c.bases],command=expr(vals['_cmd']) if '_cmd' in vals else None)
  edge(familyid,'DECLARES',cid,cs);edge(cid,'DEFINED_IN',fileid,cs)
  allclasses.append((cid,path,c,vals))
  for name,v in traits.items():
   # Only data specs describe declared parameter fields; other function calls are not parameters.
   if not (is_input or is_output):continue
   meta={kw.arg:expr(kw.value) for kw in v.keywords if kw.arg}
   ps={**source,'line_start':v.lineno,'line_end':v.end_lineno}
   pid=node('field:'+path+':'+c.name+'.'+name,'OutputField' if is_output else 'InputParameter',name,ps,owner=cid,family=family,trait=ast.unparse(v.func),metadata=meta,positional_arguments=[expr(a) for a in v.args],source_text='\n'.join(lines[v.lineno-1:v.end_lineno]))
   edge(cid,'HAS_OUTPUT_FIELD' if is_output else 'HAS_INPUT_PARAMETER',pid,ps);edge(pid,'DEFINED_IN',fileid,ps)
# Connect exact locally declared spec bindings; preserve unresolved imports/inheritance separately.
for cid,path,c,vals in allclasses:
 for key,pred in [('input_spec','ACCEPTS_SPEC'),('output_spec','RETURNS_SPEC')]:
  if key in vals:
   target='symbol:'+path+':'+ast.unparse(vals[key]);edge(cid,pred,target,nodes[cid]['source'])
 for name,v in vals.items():
  if isinstance(v,ast.Call):
   owner='field:'+path+':'+c.name+'.'+name
   if owner not in nodes:continue
   for kw in v.keywords:
    if kw.arg in ['requires','xor']:
     value=expr(kw.value)
     if isinstance(value,(list,tuple)):
      for dep in value:
       if isinstance(dep,str):edge(owner,'REQUIRES_PARAMETER' if kw.arg=='requires' else 'EXCLUSIVE_WITH','field:'+path+':'+c.name+'.'+dep,nodes[owner]['source'])
counts=collections.Counter(n['type'] for n in nodes.values());summary={'commit':commit,'source_files':sum('path' in m for m in manifest),'fetch_failures':sum('error' in m for m in manifest),'total_nodes':len(nodes),'node_types':dict(counts),'non_source_nodes':len(nodes)-counts['SourceFile'],'relations':len(edges),'quarantined_relations':len(quarantine),'alias_nodes':0,'scope':'Nipype software/API contracts for structural and shared image operations; source parsed, inherited/imported specs may be incomplete; no anatomical homology or installed-version approval','automatic_runtime_approval':False,'llm_extraction_used':False}
(R/'graph.json').write_text(json.dumps({'schema':'primatex.software_contract_graph.v1','nodes':list(nodes.values()),'edges':list(edges.values())},ensure_ascii=False,indent=2))
(R/'quarantine.json').write_text(json.dumps(quarantine,ensure_ascii=False,indent=2));(R/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
