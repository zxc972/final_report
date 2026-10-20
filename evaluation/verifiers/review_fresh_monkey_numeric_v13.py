"""Independent full-vertex and summary review; preserves frozen tolerances and raw outputs."""
from pathlib import Path
import sys,json,array,struct,math,csv,time,hashlib
import numpy as np
from scipy.spatial import ConvexHull
R=Path('/data/xuancheng/agent_overnight_20261020');sys.path.insert(0,str(R))
from independent_surface_volume import raw_surface,cortex_label,read_array,digest
RUN='monkey_fold_morphometry_autonomous_v1_20261020T154333_2c304c';D=R/'runs'/RUN
W=Path(json.loads((D/'autonomy_review.json').read_text())['workspace']);REF=R/'independent_references/new_method_tasks_20261020'
contract=json.loads((REF/'acceptance_contract.json').read_text());assert digest(REF/'acceptance_contract.json')=='83e8641b3940c48364817af0d74db9458ef6d35c82bc9f7b672bb55fb249761d'
refs=json.loads((REF/'input_reference.json').read_text());glob=json.loads((REF/'global_folding_reference.json').read_text());result=json.loads((W/'results.json').read_text())
B=Path('/data/xuancheng/featurize_20261011/data/KM002/KM002');tol=contract['checks'];counts={};fails=[];maxdiff={}
def check(category,got,expected,abs_tol=0.,rel_tol=0.,identity=''):
 counts[category]=counts.get(category,0)+1
 good=type(got)in[int,float]and math.isfinite(got)and abs(got-expected)<=abs_tol+rel_tol*abs(expected)
 if not good:fails.append({'category':category,'identity':identity,'got':got,'expected':expected,'absolute_tolerance':abs_tol,'relative_tolerance':rel_tol})
 if type(got)in[int,float]and math.isfinite(got):maxdiff[category]=max(maxdiff.get(category,0),abs(got-expected))
def morph(path):
 with path.open('rb')as f:
  assert f.read(3)==b'\xff\xff\xff';n,nf,k=struct.unpack('>3i',f.read(12));assert k==1
  return list(read_array(f,'f',n))
def weights(name):
 a=array.array('d');a.frombytes((REF/name).read_bytes());return list(a)
def annotation(path,n):
 with path.open('rb')as f:
  num=struct.unpack('>i',f.read(4))[0];assert num==n
  vals=struct.unpack('>'+str(2*num)+'i',f.read(8*num));pairs=list(zip(vals[::2],vals[1::2]));assert len(set(i for i,v in pairs))==n
  out=[None]*n
  for i,v in pairs:assert 0<=i<n;out[i]=v
  return out
def stats(xs):
 n=len(xs);avg=math.fsum(xs)/n;ordered=sorted(xs)
 def q(p):
  index=(n-1)*p;i=int(index);j=min(i+1,n-1);return ordered[i]+(index-i)*(ordered[j]-ordered[i])
 return {'mean':avg,'sd':math.sqrt(math.fsum((x-avg)**2 for x in xs)/n),'mn':ordered[0],'mx':ordered[-1],'p25':q(.25),'p50':q(.5),'p75':q(.75)}
expected={}
coverage={}
for h in ['lh','rh']:
 ref=refs['subjects']['KM002'][h];n=ref['pial']['full_vertices'];mask=cortex_label(B/'label'/(h+'.cortex.label'),n)
 pial=weights('KM002_'+h+'_pial_weights.f64');white=weights('KM002_'+h+'_white_weights.f64')
 curv=morph(B/'surf'/(h+'.curv'));sulc=morph(B/'surf'/(h+'.sulc'));thick=morph(B/'surf'/(h+'.thickness'));annot=annotation(B/'label'/(h+'.aparc.annot'),n)
 fields={'curv':curv,'sulc_mm':sulc,'thickness_mm':thick};areas={'pial_area_mm2':pial,'white_area_mm2':white}
 p=W/(h+'_vertex_metrics.csv')
 with p.open()as f:
  rows=list(csv.DictReader(f))
 check('full_vertex_row_count',len(rows),n,identity=h);seen=set()
 for row in rows:
  i=int(row['vertex_id']);assert 0<=i<n and i not in seen;seen.add(i)
  check('vertex_identity',i,len(seen)-1,identity=h+':'+str(i))
  check('cortex_membership',int(row['cortex_flag']),int(i in mask),identity=h+':'+str(i))
  check('annotation_identity',int(row['aparc_label_id']),annot[i],identity=h+':'+str(i))
  for k,xs in fields.items():check('stored_morphometry_values',float(row[k]),xs[i],tol['source_scalar_absolute_tolerance'],identity=h+':'+str(i)+':'+k)
  for k,xs in areas.items():check('per_vertex_area',float(row[k]),xs[i],tol['area_absolute_tolerance'],tol['area_relative_tolerance'],h+':'+str(i)+':'+k)
 coverage[h]={'expected':n,'actual':len(rows),'unique':len(seen),'complete':seen==set(range(n))}
 xyz,faces,meta=raw_surface(B/'surf'/(h+'.pial'));coords=np.array(xyz,dtype=np.float64).reshape(-1,3);hc=ConvexHull(coords[sorted(mask)])
 exp={'nvert':n,'ncortex':len(mask),'total_pial':ref['pial']['area']['area'],'total_white':ref['white']['area']['area'],'ctx_pial':ref['pial']['cortex_vertex_share_area'],'ctx_white':ref['white']['cortex_vertex_share_area'],
 'hull_area':glob['subjects']['KM002'][h]['hull_area_heron'],'gi':glob['subjects']['KM002'][h]['global_hull_ratio'],'gi_ctx':ref['pial']['cortex_vertex_share_area']/hc.area,'sum_varea_pial':math.fsum(pial),'sum_varea_white':math.fsum(white)}
 for label,values in [('curv',curv),('sulc',sulc),('thick',thick),('area',pial)]:exp[label]=stats([values[i]for i in mask])
 expected[h]=exp
 for k,v in exp.items():
  if isinstance(v,dict):
   for metric,target in v.items():check('full_precision_summary',result['perhemi'][h][k][metric],target,tol['derived_summary_absolute_tolerance'],tol['derived_summary_relative_tolerance'],h+':'+k+':'+metric)
  elif k in ['gi','gi_ctx']:check('full_precision_folding',result['perhemi'][h][k],v,tol['dimensionless_folding_absolute_tolerance'],identity=h+':'+k)
  else:check('full_precision_summary',result['perhemi'][h][k],v,tol['derived_summary_absolute_tolerance'],tol['derived_summary_relative_tolerance'],h+':'+k)
mapping={'n_cortex_vertices':('ncortex',),'pial_area_mm2':('ctx_pial',),'white_area_mm2':('ctx_white',),'total_pial_area_mm2':('total_pial',),'total_white_area_mm2':('total_white',),'hull_area_mm2':('hull_area',),'gyrification_index_global_pial':('gi',),'gi_cortex_pial':('gi_ctx',),'curv_mean':('curv','mean'),'curv_sd':('curv','sd'),'curv_p50':('curv','p50'),'sulc_mean_mm':('sulc','mean'),'sulc_sd':('sulc','sd'),'sulc_p50':('sulc','p50'),'sulc_min':('sulc','mn'),'sulc_max':('sulc','mx'),'vertex_area_mean_mm2':('area','mean')}
for row in csv.DictReader((W/'morphometry_summary.tsv').open(),delimiter='\t'):
 h=row['hemisphere']
 for col,path in mapping.items():
  value=expected[h]
  for part in path:value=value[part]
  if col in ['gyrification_index_global_pial','gi_cortex_pial']:
   check('published_table_folding',float(row[col]),value,tol['dimensionless_folding_absolute_tolerance'],identity=h+':'+col)
  else:check('published_table_summary',float(row[col]),value,tol['derived_summary_absolute_tolerance'],tol['derived_summary_relative_tolerance'],h+':'+col)
out={'run':RUN,'created':time.time(),'contract_sha256':digest(REF/'acceptance_contract.json'),'field_mapping_basis':'Read and froze interpretation from actual compute_core.py before comparing; cortex subset; ddof0; NumPy default linear quantiles. No closest-answer choice or tolerance change.','coverage':coverage,'counts':counts,'total_checks':sum(counts.values()),'maximum_absolute_differences':maxdiff,'failures':fails,'all_numeric_contracts_passed':not fails,
 'primary_full_vertex_and_full_precision_passed':not any(f['category']not in ['published_table_folding']for f in fails),
 'shared_hull_dependency':'SciPy/Qhull author algorithm shared; separately scalar Heron area sum. Not a fully independent convex-hull algorithm.',
 'scope':'Stored-coordinate arithmetic and file identity only; no expert anatomy QC, physical-scale approval, species validation or biological homology approval.'}
target=D/'independent_new_method_numeric_review.json';assert not target.exists();target.write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2))

