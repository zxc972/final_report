"""Pre-task AI-assisted semantic correction of method evidence; never uses analysis outputs."""
from pathlib import Path
import collections,copy,hashlib,json,re,shutil,time
R=Path('/data/xuancheng/agent_overnight_20261020');P=R/'method_graph_loop_20261020';A=R/'research_evidence_v12';D=R/'research_evidence_v13'
assert not D.exists();shutil.copytree(A,D)
bundle=json.loads((A/'method_graph.json').read_text());methods=bundle['methods'];sources={s['id']:s for s in bundle['sources']}
for s in json.loads((P/'statistics_source_manifest.json').read_text()):
 if s['status']=='downloaded':sources[s['id']]=s
def evidence(sid,quote):
 text=(P/'sources'/(sid+'.txt')).read_text();pos=text.find(quote);assert pos>=0,(sid,quote)
 lo=text.count('\n',0,pos)+1;hi=text.count('\n',0,pos+len(quote))+1
 return {'path':'method_'+sid+'.txt','sha256':hashlib.sha256(text.encode()).hexdigest(),'line_start':lo,'line_end':hi,'text_sha256':hashlib.sha256('\n'.join(text.splitlines()[lo-1:hi]).encode()).hexdigest()}
def linequote(sid,needle):
 lines=(P/'sources'/(sid+'.txt')).read_text().splitlines()
 line=next(x for x in lines if needle in x)
 if len(line)<=450:return line
 p=line.index(needle);return line[max(0,p-45):min(len(line),p+len(needle)+100)]
def fact(statement,sid,needle,kind='direct'):
 q=linequote(sid,needle);return {'statement':statement,'source_id':sid,'quote':q,'claim_type':kind,'evidence':evidence(sid,q)}
quarantine=[];corrections=[]
old=next(m for m in methods if 'global_surface_folding'in m['id']);methods.remove(old)
# A pure global hull-ratio method, separate from coarse-graining/fractal fitting.
gi={'id':'method:v13:global_convex_hull_gyrification','name':'Global pial-to-convex-hull area ratio','purpose':'Whole-hemisphere global folding descriptor and scale sensitivity analysis. This is not FreeSurfer localGI, alpha-surface local depth, or proof of biological group differences.','software':['NiBabel','NumPy','SciPy ConvexHull'],'species_scope':'Geometric descriptor on supplied cortical surfaces; source examples do not establish current species identity or anatomical validity.','source_ids':['global_gyrification','scipy_hull','nibabel_fs','trimesh_triangles','comparative_folding','fs_lgi'],'scientific_status':'not_expert_reviewed','executable':False,'coverage_status':'AI_assisted_source_composition_originals_available'}
gi['inputs']=[fact('Triangular pial surface coordinates and connectivity; preserve the stated hemisphere and mesh coverage.','nibabel_fs','Read a triangular format Freesurfer surface mesh.','application_inference')]
gi['conditions']=[fact('For a three-dimensional hull, ConvexHull.area represents surface area; its two-dimensional interpretation is perimeter.','scipy_hull','Surface area of the convex hull when input dimension > 2.'),
 fact('The area ratio uses total folded surface area and the area of the convex hull of that same surface.','global_gyrification','the ratio of the surface area to the area of the convex hull.'),
 fact('Inspect reconstructed surface validity and record QC limitations rather than infer it from successful computation.','comparative_folding','quality checked by visual inspection','application_inference')]
gi['steps']=[fact('Read geometry as coordinates and triangle connectivity.','nibabel_fs','Read a triangular format Freesurfer surface mesh.'),
 fact('Compute and sum the triangle areas on the chosen complete surface.','trimesh_triangles','Calculates the sum area of input triangles','application_inference'),
 fact('Construct a convex hull of the same three-dimensional pial coordinates.','scipy_hull','Coordinates of points to construct a convex hull from','application_inference'),
 fact('Read the hull surface area and compute total pial area divided by hull area.','global_gyrification','the ratio of the surface area to the area of the convex hull.','application_inference')]
gi['checks']=[fact('Check geometric degeneracy and record any actual Qhull errors.','scipy_hull','Raised when Qhull encounters an error condition','application_inference'),
 fact('Check the dimensionless ratio under isotropic coordinate rescaling; report the actual result without changing input data.','comparative_folding','leaves all dimensionless shape properties unaffected','application_inference'),
 fact('Check that both area terms refer to the same input surface and coverage.','global_gyrification','the ratio of the surface area to the area of the convex hull.','application_inference')]
gi['exceptions']=[fact('Do not identify this whole-surface convex-hull ratio with the localGI circular-ROI method.','fs_lgi','Local Gyrification Index addresses these issues by quantifying Gyrification Index in circular three-dimensional regions of interest.','application_inference'),
 fact('A successful numeric ratio is not the visual anatomical inspection described in the source.','comparative_folding','quality checked by visual inspection','application_inference')]
gi['outputs']=[fact('A dimensionless global folding ratio with separately reported total and hull areas.','global_gyrification','the ratio of the surface area to the area of the convex hull.','application_inference')]
gi['parameters']=[];methods.append(gi)
sc=copy.deepcopy(old);sc['id']='method:v13:coarse_grained_fractal_scaling';sc['name']='Cortical coarse-graining and fractal scaling analysis';sc['purpose']='Specific multi-scale coarse-graining algorithm from the eLife study; do not append its requirements or empirical findings to a simple global hull-ratio workflow.'
for cat in ['inputs','conditions','steps','checks','exceptions','outputs','parameters']:
 sc[cat]=[c for c in sc.get(cat,[])if c['source_id']=='comparative_folding']
sc['checks']=[c for c in sc['checks']if not re.search(r'R.?2|scaling law|K remains',c['statement'],re.I)]
sc['source_ids']=['comparative_folding'];sc['scope_note']='Paper-specific procedure. Its observed R2/K results are findings, not universal pass thresholds.'
methods.append(sc)
for c in old['checks']:
 if re.search(r'R.?2|K remains',c['statement'],re.I):quarantine.append({'method_id':old['id'],'claim':c,'reason':'Author-reported study outcome cannot be converted into universal QA threshold'})
corrections.append({'id':'MF01','issue':'Global convex hull ratio, alpha hull and coarse-graining were conflated','action':'Separate two explicit methods; do not expose old combined recipe in active release'})
corrections.append({'id':'MF02','issue':'Author study outcomes became generic verification checks','action':'Quarantine R2 and K outcome-derived QA assertions'})
curv=next(m for m in methods if 'existing_curvature_sulc_profile'in m['id'])
for category in ['conditions','steps','checks','exceptions']:
 for claim in curv[category]:quarantine.append({'method_id':curv['id'],'claim':claim,'reason':'Broad inference not adequately entailed by quoted filename/processing stage; replaced with explicit format-level method'})
curv.update(name='Distribution analysis of supplied vertex morphometry',purpose='Read provided curv/sulc-like morphometry as stored fields, check mesh identity and describe distributions. Generator, units, smoothing and biological interpretation require their own provenance; no implicit alpha-distance equivalence.',source_ids=['nibabel_fs','numpy_average','numpy_histogram','fs_morph'],species_scope='Format-level method, no species validation',scope_note='Derived application workflow using documented I/O and descriptive statistics; not a claim to reconstruct curvature or infer physical sulcal-depth units.')
curv['inputs']=[fact('Provided FreeSurfer-format per-vertex morphometry files.','nibabel_fs','This function reads in what Freesurfer internally calls'),
 fact('Corresponding triangular mesh and vertex identities.','nibabel_fs','Read a triangular format Freesurfer surface mesh.','application_inference')]
curv['conditions']=[fact('Verify a one-to-one relationship between stored per-vertex values and the selected mesh, using actual lengths and identifiers.','nibabel_fs','nvtx x 3 array of vertex','application_inference'),
 fact('If a cortex label is used, treat it as an included vertex-index subset and preserve full vertex identity separately.','nibabel_fs','Array with indices of vertices included in label.','application_inference')]
curv['steps']=[fact('Read the supplied morphometry vector with read_morph_data.','nibabel_fs','nibabel.freesurfer.io.read_morph_data('),
 fact('Read mesh geometry and, if used, the cortex label membership.','nibabel_fs','Read a triangular format Freesurfer surface mesh.','application_inference'),
 fact('Compute declared unweighted or explicitly weighted averages; retain the actual weighting definition.','numpy_average','Compute the weighted average','application_inference'),
 fact('Compute histograms using declared bins, weights and density conventions.','numpy_histogram','Compute the histogram of a dataset.','application_inference')]
curv['checks']=[fact('When weights are used, check the weighting vector and nonzero weight sum; a zero weight sum is an error.','numpy_average','ZeroDivisionError','application_inference'),
 fact('Report density versus counts consistently with histogram arguments.','numpy_histogram','density','application_inference')]
curv['exceptions']=[fact('The morphometry file format alone does not establish the source algorithm, species, smoothing kernel, or physical units.','nibabel_fs','This function reads in what Freesurfer internally calls','application_inference')]
curv['outputs']=[fact('Descriptive summaries and histogram data with explicit coverage, weights and conventions.','numpy_histogram','Compute the histogram of a dataset.','application_inference')];curv['parameters']=[]
corrections.append({'id':'MF03','issue':'A sulc filename or binary format was treated as evidence of actual generator and physical definition','action':'Restrict active method to stored-field distribution analysis; require separate provenance'})
for m in methods:
 if 'hcp_structural_pipeline'in m['id']:
  for c in m['conditions']:c['scope']='source_case_context_not_universal_requirement'
  m['scope_note']='Personal tutorial versions, OS and resource examples are source case context. Do not turn them into universal required software/OS limits.'
corrections.append({'id':'MF04','issue':'Personal tutorial tested OS/version was liable to become a universal prerequisite','action':'Mark source-case conditions as non-universal context'})
# Rebuild active method neighborhood from the corrected cards.
nodes=[];edges=[]
for sid,s in sources.items():
 text=(P/'sources'/(sid+'.txt')).read_text();assert hashlib.sha256(text.encode()).hexdigest()==s['text_sha256']
 (D/'sources'/('method_'+sid+'.txt')).write_text(text)
 nodes.append({'id':'method-source:'+sid,'type':'SourceDocument','name':sid.replace('_',' '),'url':s['url'],'source_paths':['method_'+sid+'.txt'],'review_status':'source_snapshot_candidate','scientific_status':'not_expert_reviewed','executable':False})
types={'inputs':('InputRequirement','REQUIRES_INPUT'),'conditions':('ApplicabilityCondition','HAS_CONDITION'),'steps':('AnalysisStep','HAS_STEP'),'checks':('VerificationCheck','VERIFIED_BY'),'exceptions':('MethodException','HAS_EXCEPTION'),'outputs':('OutputArtifact','PRODUCES'),'parameters':('MethodParameter','HAS_PARAMETER')}
seen={}
for m in methods:
 mid=m['id'];nodes.append({'id':mid,'type':'AnalysisMethod','name':m['name'],'species_scope':m['species_scope'],'metadata':{'purpose':m['purpose'],'software':m['software']},'review_status':'AI_assisted_semantic_candidate','scientific_status':'not_expert_reviewed','executable':False})
 for cat,(typ,rel)in types.items():
  for order,c in enumerate(m[cat]):
   assert c['quote']in(P/'sources'/(c['source_id']+'.txt')).read_text()
   key=(typ,mid,re.sub(r'\s+',' ',c['statement']).strip().lower())
   nid=seen.get(key)
   if not nid:
    nid='method-fact:'+hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24];seen[key]=nid
    nodes.append({'id':nid,'type':typ,'name':c['statement'],'evidence':[c['evidence']],'metadata':{'method_id':mid,'claim_type':c['claim_type'],'source_id':c['source_id'],'source_quote':c['quote']},'review_status':'AI_assisted_semantic_candidate','scientific_status':'not_expert_reviewed','executable':False})
    edges.append({'source':nid,'target':'method-source:'+c['source_id'],'type':'SUPPORTED_BY','evidence':[c['evidence']]})
   c['id']=nid;edges.append({'source':mid,'target':nid,'type':rel,'order':order})
  if cat=='steps':
   for a,b in zip(m[cat],m[cat][1:]):edges.append({'source':a['id'],'target':b['id'],'type':'NEXT_DOCUMENTED_STEP'})
 for sid in m['source_ids']:edges.append({'source':mid,'target':'method-source:'+sid,'type':'DOCUMENTED_IN'})
out={'schema':'primatex.method_graph.v1','created':time.time(),'methods':methods,'nodes':nodes,'edges':edges,'sources':list(sources.values()),'review_scope':'AI-assisted pre-task semantic correction, not expert blind review; no study results used.'}
(D/'method_graph.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
domain=json.loads((R/'research_evidence_v11'/'domain_graph.json').read_text());domain['nodes']+=nodes;domain['edges']+=edges
ids={n['id']for n in domain['nodes']};assert len(ids)==len(domain['nodes'])and all(e['source']in ids and e['target']in ids for e in domain['edges'])
(D/'domain_graph.json').write_text(json.dumps(domain,ensure_ascii=False,indent=2))
docs=json.loads((A/'documents.json').read_text())
for sid in ['numpy_average','numpy_histogram']:
 s=sources[sid];text=(P/'sources'/(sid+'.txt')).read_text()
 docs.append({'id':'METHOD_SOURCE_'+sid,'url':s['url'],'heading':sid.replace('_',' ')+' method source original','text':text,'text_sha256':s['text_sha256'],'source_scope':'Author API snapshot, not installed-version or study suitability validation'})
(D/'documents.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2))
cfg=json.loads((D/'config.json').read_text());cfg.update(created=time.time(),predecessor='research_evidence_v12',sources=len(docs))
for fn,key in [('method_graph.json','method_graph_sha256'),('domain_graph.json','domain_graph_sha256'),('documents.json','documents_sha256')]:cfg[key]=hashlib.sha256((D/fn).read_bytes()).hexdigest()
cfg['snapshot_files']={str(p.relative_to(D)):hashlib.sha256(p.read_bytes()).hexdigest()for p in D.rglob('*')if p.is_file()and p.name!='config.json'}
(D/'config.json').write_text(json.dumps(cfg,indent=2))
audit={'time':time.time(),'release':D.name,'method_cards':len(methods),'new_method_nodes':len(nodes),'new_method_edges':len(edges),'new_types':dict(collections.Counter(n['type']for n in nodes)),'total_mixed_nodes':len(domain['nodes']),'total_edges':len(domain['edges']),'label_nodes':1791,'parent_snapshots':len(docs),'unique_urls':len({d['url']for d in docs}),'semantic_corrections':corrections,'additional_quarantined_claims':len(quarantine),'expert_review':False,'native_index_changed':False,'science_results_used_for_curation':False}
(P/'semantic_correction_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));(P/'semantic_quarantine.json').write_text(json.dumps(quarantine,ensure_ascii=False,indent=2))
print(json.dumps(audit,ensure_ascii=False,indent=2))

