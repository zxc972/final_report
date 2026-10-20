"""Primary source, task-driven volume/surface evidence; no Agent/model calls."""
from pathlib import Path
import json,hashlib,time,html.parser,urllib.request,shutil,concurrent.futures,collections
R=Path('/data/xuancheng/agent_overnight_20261020');D=R/'research_evidence_v10';assert not D.exists();C=R/'surface_volume_sources_v10';C.mkdir(exist_ok=False)
class Plain(html.parser.HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.a=[];self.skip=0
 def handle_starttag(self,t,a):
  if t in ['script','style']:self.skip+=1
  if t in ['p','div','li','h1','h2','h3','pre','br','dt','dd','tr']:self.a.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style']:self.skip=max(0,self.skip-1)
 def handle_data(self,s):
  if not self.skip:self.a.append(s)
urls={'FS_VOL2SURF':'https://surfer.nmr.mgh.harvard.edu/fswiki/mri_vol2surf','NIB_FS':'https://nipy.org/nibabel/reference/nibabel.freesurfer.html'}
def fetch(k):
 with urllib.request.urlopen(urllib.request.Request(urls[k],headers={'User-Agent':'PrimateX primary reference collector'}),timeout=35)as f:b=f.read(1500000)
 p=Plain();p.feed(b.decode());ls=[x.strip()for x in ''.join(p.a).splitlines()if x.strip()];text='\n'.join(ls);(C/(k+'.html')).write_bytes(b);(C/(k+'.txt')).write_text(text);return {'id':k,'url':urls[k],'raw_sha256':hashlib.sha256(b).hexdigest(),'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'fetched':time.time()}
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as ex:prov=list(ex.map(fetch,urls))
(C/'provenance.json').write_text(json.dumps(prov,indent=2));shutil.copytree(R/'research_evidence_v9',D);docs=json.loads((D/'documents.json').read_text());g=json.loads((D/'domain_graph.json').read_text());new=[];edges=[];parents={}
fs=(C/'FS_VOL2SURF.txt').read_text().splitlines();start=next(i for i,x in enumerate(fs)if x.startswith('mri_vol2surf - assigns'));fs='\n'.join(fs[start:])
nib=(C/'NIB_FS.txt').read_text().splitlines();i=next(i for i,x in enumerate(nib)if x.startswith('nibabel.freesurfer.io.read_geometry('));j=next(i for i,x in enumerate(nib)if x.startswith('nibabel.freesurfer.io.read_label('));geom='\n'.join(nib[i:j]);m=next(i for i,x in enumerate(nib)if x.startswith('class nibabel.freesurfer.mghformat.MGHHeader('));n=next(i for i,x in enumerate(nib)if x.startswith('class nibabel.freesurfer.mghformat.MGHImage('));mgh='\n'.join(nib[m:n])
entries=[('VOL2SURF','FS_VOL2SURF',fs,'FreeSurfer mri_vol2surf volume to surface sampling registration float2int projection output scalar reshape geometry caveat'),('NIB_GEOMETRY','NIB_FS',geom,'NiBabel freesurfer read_geometry read_metadata surface vertices faces volume_info voxel size xras yras zras cras'),('NIB_MGH','NIB_FS',mgh,'NiBabel MGHHeader get_vox2ras_tkr Torig get_affine get_vox2ras get_ras2vox coordinate transforms')]
for key,owner,text,title in entries:
 rel='coord_'+key+'.txt';(D/'sources'/rel).write_text(text);parents[key]={'path':rel,'text':text,'owner':owner};docs.append({'id':'COORD_'+key,'url':urls[owner],'heading':title,'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'source_scope':'Task-scoped original API/command section. FreeSurfer wiki last edited2008; installed7.2.0 help required for actual flags. NiBabel rolling reference separate from installed5.4.2. Lexical/domain addition, not native LightRAG reindex; scientific applicability not expert reviewed.'})
for key in urls:
 files=[v['path']for v in parents.values()if v['owner']==key];new.append({'id':'source:COORD:'+key,'type':'SourceDocument','name':key,'url':urls[key],'source_paths':files,'review_status':'source_parsed_candidate','scientific_status':'not_expert_reviewed','executable':False})
def ev(k,needle,before=0,after=3):
 p=parents[k];ls=p['text'].splitlines();i=next(i for i,x in enumerate(ls)if needle in x);lo=max(0,i-before);hi=min(len(ls),i+after+1);return {'path':p['path'],'sha256':hashlib.sha256(p['text'].encode()).hexdigest(),'line_start':lo+1,'line_end':hi,'text_sha256':hashlib.sha256('\n'.join(ls[lo:hi]).encode()).hexdigest()}
def node(key,typ,name,parent,needle,meta=None,before=0,after=3):
 e=ev(parent,needle,before,after);id='coord:'+key;new.append({'id':id,'type':typ,'name':name,'evidence':[e],'metadata':meta or{},'review_status':'AI_assisted_source_candidate','scientific_status':'not_expert_reviewed','executable':False});edges.append({'source':id,'target':'source:COORD:'+parents[parent]['owner'],'type':'SUPPORTED_BY','evidence':[e]});return id
v=node('method:vol2surf','MethodEntrypoint','FreeSurfer mri_vol2surf maps volume samples to surface vertices','VOL2SURF','mri_vol2surf - assigns',{'entrypoint':'mri_vol2surf','version_scope':'Old wiki flags require installed help check'})
t=node('method:tkr','MethodEntrypoint','MGHHeader.get_vox2ras_tkr returns vox2ras-tkr Torig','NIB_MGH','get_vox2ras_tkr()',{'owner':'nibabel.freesurfer.mghformat.MGHHeader','context_source':'POST_FS_COORDS already registered'})
r=node('method:read_geometry','MethodEntrypoint','NiBabel read_geometry reads mesh and optionally volume metadata','NIB_GEOMETRY','nibabel.freesurfer.io.read_geometry(',{'entrypoint':'nibabel.freesurfer.io.read_geometry'},after=8)
for key,name,parent,needle,owner,meta,bef,aft in [
 ('registration','Volume-to-surface mapping requires a registration to the subject; filename alone does not verify geometry lineage','VOL2SURF','source registration file',v,{'application_inference':'Registration requirement direct; lineage interpretation is our explicit applicability rule.'},0,4),
 ('rounding','Voxel sampling float-to-integer convention must match registration; do not silently equate tkregister and round','VOL2SURF','float-to-int conversion method',v,{},0,4),
 ('scalar_output','Volume-to-surface result is a vertex-indexed scalar array; reshaped output header geometry is not anatomical volume geometry','VOL2SURF','Any geometry information saved',v,{},0,2),
 ('projection','projfrac uses cortical-thickness fraction and requires the subject thickness file, whereas projdist is a distance','VOL2SURF','fractional projection',v,{},0,3),
 ('surface_metadata','read_geometry with read_metadata returns volume_info including dimensions, voxel sizes, directions and center; inspect before binding volume coordinates','NIB_GEOMETRY','Valid keys:',r,{'application_inference':'Fields direct; geometric compatibility comparison is task-specific, not established by successful parsing.'},3,13),
 ('mgh_affine','MGH affine is reconstructed from delta, Mdc, Pxyz_c and dimensions; scanner affine is distinct from vox2ras-tkr','NIB_MGH','MGH format doesn',t,{'application_inference':'API definitions and distinct functions; verify actual coordinate convention and input history, do not infer species/physical scale from a filename.'},2,3)]:
 c=node('condition:'+key,'ApplicabilityCondition',name,parent,needle,meta,bef,aft);edges.append({'source':owner,'target':c,'type':'HAS_CONDITION'})
for key,needle in [('hemi','hemisphere (lh or rh)'),('surf','target surface (white)'),('projdist','distance projection along normal')]:
 q=node('parameter:'+key,'ParameterDefinition','--'+key,'VOL2SURF',needle,{'owner':'mri_vol2surf'},before=1,after=2);edges.append({'source':v,'target':q,'type':'HAS_PARAMETER'})
ids={x['id']for x in g['nodes']};assert not ids&{x['id']for x in new};g['nodes']+=new;g['edges']+=edges;ids={x['id']for x in g['nodes']};assert len(ids)==len(g['nodes'])and all(e['source']in ids and e['target']in ids for e in g['edges'])
for x in new:
 for e in x.get('evidence',[]):
  b=(D/'sources'/e['path']).read_bytes();assert hashlib.sha256(b).hexdigest()==e['sha256'];assert hashlib.sha256('\n'.join(b.decode().splitlines()[e['line_start']-1:e['line_end']]).encode()).hexdigest()==e['text_sha256']
(D/'documents.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2));(D/'domain_graph.json').write_text(json.dumps(g,ensure_ascii=False,indent=2));cfg=json.loads((D/'config.json').read_text());cfg.update(created=time.time(),predecessor='research_evidence_v9',supersedes_candidate='research_evidence_v9',sources=len(docs),documents_sha256=hashlib.sha256((D/'documents.json').read_bytes()).hexdigest(),domain_graph_sha256=hashlib.sha256((D/'domain_graph.json').read_bytes()).hexdigest(),native_graph='Frozen native unchanged. v10 scoped surface/volume original sections and typed domain applicability overlay.',snapshot_files={str(p.relative_to(D)):hashlib.sha256(p.read_bytes()).hexdigest()for p in D.rglob('*')if p.is_file()and p.name!='config.json'});(D/'config.json').write_text(json.dumps(cfg,indent=2));a={'time':time.time(),'release':D.name,'parents':len(docs),'unique_urls':len({d['url']for d in docs}),'domain_nodes':len(g['nodes']),'domain_edges':len(g['edges']),'new_nodes':len(new),'new_edges':len(edges),'new_types':dict(collections.Counter(x['type']for x in new)),'new_unique_urls':2,'new_parent_sections':3,'new_source_documents':2,'provider_calls':0,'native_LLM_reindex':False,'evidence_hashes_match':True,'old_v9_active_pve_run_untouched':True,'review':'AI-assisted source relevance review, not expert anatomical QC or homology approval'};(R/'audit/research_v10_count_audit.json').write_text(json.dumps(a,indent=2));print(json.dumps(a,indent=2))
