"""Independent post-run cross-dataset descriptor checks, with frozen original precision."""
from pathlib import Path
import sys,csv,json,math,time,collections
import numpy as np
from scipy.spatial import ConvexHull
R=Path('/data/xuancheng/agent_overnight_20261020');sys.path.insert(0,str(R))
from independent_surface_volume import raw_surface,digest
RUN='crossspecies_global_folding_autonomous_v1_20261020T160050_5ab0c7';D=R/'runs'/RUN
W=Path(json.loads((D/'autonomy_review.json').read_text())['workspace']);REF=R/'independent_references/new_method_tasks_20261020'
assert digest(REF/'acceptance_contract.json')=='83e8641b3940c48364817af0d74db9458ef6d35c82bc9f7b672bb55fb249761d'
contract=json.loads((REF/'acceptance_contract.json').read_text());tol=contract['checks'];ref=json.loads((REF/'global_folding_reference.json').read_text())
counts=collections.Counter();failures=[];rounding_fail=[];maximum={}
def check(cat,got,expected,at=0.,rt=0.,key=''):
 counts[cat]+=1;delta=abs(got-expected)
 maximum[cat]=max(maximum.get(cat,0),delta)
 if not math.isfinite(got)or delta>at+rt*abs(expected):failures.append({'category':cat,'identity':key,'got':got,'expected':expected,'absolute_tolerance':at,'relative_tolerance':rt})
roots={'KM002':Path('/data/xuancheng/featurize_20261011/data/KM002/KM002')}
roots.update({s:Path('/data/xuancheng/human_fastsurfer/subjects')/s for s in ['100610','101309','101410']})
topologies={};extrema={}
for sid,root in roots.items():
 for hemi in ['lh','rh']:
  p=root/'surf'/(hemi+'.pial');assert p.resolve().is_relative_to(root.resolve())
  xyz,f,meta=raw_surface(p);xyz=np.array(xyz,dtype=np.float64).reshape(-1,3);faces=np.array(f,dtype=np.int64).reshape(-1,3)
  es=collections.Counter()
  parent=list(range(meta['n_vertices']))
  def find(x):
   while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
   return x
  for tri in faces:
   i,j,k=map(int,tri)
   for a,b in [(i,j),(j,k),(k,i)]:
    es[min(a,b),max(a,b)]+=1
    ra,rb=find(a),find(b)
    if ra!=rb:parent[ra]=rb
  zero=0
  for start in range(0,len(faces),20000):
   tri=xyz[faces[start:start+20000]]
   zero+=int((np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)==0).sum())
  topologies[sid,hemi]={'n_vertices':meta['n_vertices'],'n_faces':meta['n_faces'],'unique_edges':len(es),'boundary_edges':sum(n==1 for n in es.values()),'nonmanifold_edges':sum(n!=2 for n in es.values()),'euler_characteristic':meta['n_vertices']-len(es)+meta['n_faces'],'connected_components':len({find(x)for x in range(meta['n_vertices'])}),'n_degenerate_faces':zero}
  extrema[sid,hemi]=[xyz.min(axis=0).tolist(),xyz.max(axis=0).tolist()]
rows=list(csv.DictReader((W/'folding_summary.tsv').open(),delimiter='\t'));check('native_row_count',len(rows),8)
seen=set()
for row in rows:
 sid,h=row['subject'],row['hemisphere'];assert(sid,h)not in seen;seen.add((sid,h));e=ref['subjects'][sid][h];t=topologies[sid,h];key=sid+':'+h
 for k in ['n_vertices','n_faces','n_degenerate_faces']:check('native_integer_qc',int(row[k]),t[k],key=key+':'+k)
 check('native_closed_flag',int(row['closed_genus0_sphere']=='True'),int(t['boundary_edges']==0 and t['nonmanifold_edges']==0 and t['connected_components']==1 and t['euler_characteristic']==2),key=key)
 for col,refkey in [('pial_area_mm2','pial_area'),('hull_area_mm2','hull_area_heron')]:
  check('native_area',float(row[col]),e[refkey],tol['area_absolute_tolerance'],tol['area_relative_tolerance'],key+':'+col)
  if abs(float(row[col])-round(e[refkey],3))>1e-9:rounding_fail.append(key+':'+col)
 check('native_GI',float(row['global_GI']),e['global_hull_ratio'],tol['dimensionless_folding_absolute_tolerance'],key=key)
 if abs(float(row['global_GI'])-round(e['global_hull_ratio'],4))>1e-9:rounding_fail.append(key+':global_GI')
 for axis,n in enumerate(['x','y','z']):
  for pos,label in [(0,'min'),(1,'max')]:check('native_coordinate_extrema',float(row['coords_'+label+'_'+n]),extrema[sid,h][pos][axis],tol['source_scalar_absolute_tolerance'],key=key+':'+label+n)
scale=list(csv.DictReader((W/'scale_sensitivity.tsv').open(),delimiter='\t'));check('scale_row_count',len(scale),40);scale_keys=set()
for row in scale:
 sid,h=row['subject'],row['hemisphere'];s=float(row['scale_factor']);key=sid+':'+h+':'+str(s);assert(sid,h,s)not in scale_keys;scale_keys.add((sid,h,s));e=ref['subjects'][sid][h]
 for col,k in [('pial_area_mm2','pial_area'),('hull_area_mm2','hull_area_heron')]:
  expected=e[k]*s*s;check('scaled_area',float(row[col]),expected,tol['area_absolute_tolerance'],tol['area_relative_tolerance'],key+':'+col)
  if abs(float(row[col])-round(expected,3))>1e-8:rounding_fail.append(key+':'+col)
 check('scaled_GI',float(row['global_GI']),e['global_hull_ratio'],tol['dimensionless_folding_absolute_tolerance'],key=key)
 check('scale_relative_change',float(row['rel_change_vs_native']),0.,tol['scale_invariance_relative_tolerance'],key=key)
 if abs(float(row['global_GI'])-round(e['global_hull_ratio'],4))>1e-9:rounding_fail.append(key+':GI')
expectedkeys={(s,h,k)for s in roots for h in ['lh','rh']for k in [.25,.5,2.,4.,10.]}
out={'run':RUN,'created':time.time(),'contract_sha256':digest(REF/'acceptance_contract.json'),'field_mapping_basis':'Actual folding_main.py and table headers, whole pial meshes, same vertices for hull; no closest-answer selection or tolerance changes.',
 'coverage':{'native_meshes':len(seen),'native_complete':seen=={(s,h)for s in roots for h in ['lh','rh']},'scale_rows':len(scale),'scale_complete':scale_keys==expectedkeys},
 'checks':dict(counts),'total_checks':sum(counts.values()),'maximum_absolute_differences':maximum,'failures':failures,'all_original_precision_contracts_passed':not failures,
 'declared_export_rounding_reproduction':{'matches':not rounding_fail,'failures':rounding_fail,'scope':'Secondary reproduction of explicit code rounding, NOT replacement for original frozen precision acceptance.'},
 'independent_topology':{sid+':'+h:v for(sid,h),v in topologies.items()},'scale_invariance_check_passed':not any(f['category']=='scale_relative_change'for f in failures),
 'scope':'Stored-coordinate descriptors only; same Qhull author algorithm for hull dependency, separate raw parser/Heron area and explicit topology checks. No expert QC, species/homology or biological inference approval.'}
p=D/'independent_new_method_numeric_review.json';assert not p.exists();p.write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in out.items()if k not in ['failures','independent_topology']},ensure_ascii=False,indent=2));print(json.dumps({'failure_counts':dict(collections.Counter(f['category']for f in failures))},indent=2))

