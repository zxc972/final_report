"""E1 host-only verifier. Never mount source, private reference or grading output in /work.
Pass iff original requested coverage and independent numeric values match, and
existing native contract, review and conclusion gates all pass. Negative tasks
require a separately recorded grounded semantic refusal audit, not keyword success.
"""
from __future__ import annotations
import argparse,copy,csv,hashlib,importlib.util,json,math,re,sys,types
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
BACKEND=REPO/'agent/modules/agent/backend'
package=types.ModuleType('_e1_reference');package.__path__=[str(BACKEND)];sys.modules[package.__name__]=package
def module(name):
 key=package.__name__+'.'+name
 if key not in sys.modules:
  spec=importlib.util.spec_from_file_location(key,BACKEND/(name+'.py'));m=importlib.util.module_from_spec(spec);sys.modules[key]=m;spec.loader.exec_module(m)
 return sys.modules[key]
numeric=module('analysis_numeric_reference');independent=module('analysis_independent_numeric');global_ref=module('analysis_global_reference');stats=module('analysis_group_stats')
ATOL,RTOL=independent.ATOL,independent.RTOL
METRICS=['brain_volume_mm3','etiv_mm3','total_area_mm2','mean_thickness_mm','hull_ratio']
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def roi(root,sid):
 rows=[]
 for h in ('lh','rh'):
  labels,names=numeric.read_annotation(root/'label'/(h+'.aparc.DKTatlas.annot'))
  cortex=numeric.read_cortex(root/'label'/(h+'.cortex.label'),len(labels));values=numeric.read_metric(root/'surf'/(h+'.thickness'))
  assert len(values)==len(labels)
  for key,name in sorted(names.items()):
   if key<0 or re.sub('[^a-z]','',name.lower()) in ('unknown','medialwall','corpuscallosum'):continue
   indices=[i for i in sorted(cortex) if labels[i]==key]
   if indices:rows.append({'subject':sid,'hemisphere':h,'metric':'thickness','label_key':key,'name':name,**numeric.summarize([values[i] for i in indices])})
 return rows

def globals_(entry):
 root=Path(entry['path']);nonhuman=entry['species_declared']=='rhesus';scale=entry['scale_observation']
 request={'species':'rhesus' if nonhuman else 'human','scale_k':scale['k'],'rescaled':scale['rescaled'],'scale_state':scale.get('status'),'pial':{h:str(root/'surf'/(h+'.pial')) for h in ('lh','rh')}}
 if nonhuman:
  request.update(mask_volume=str(root/'mri/brainmask.mgz'),white={h:str(root/'surf'/(h+'.white')) for h in ('lh','rh')},thickness={h:str(root/'surf'/(h+'.thickness')) for h in ('lh','rh')},cortex_labels={h:str(root/'label'/(h+'.cortex.label')) for h in ('lh','rh')})
 else:
  request.update(aseg_stats=str(root/'stats/aseg.stats'),hemi_stats={h:str(root/'stats'/(h+'.aparc.stats')) for h in ('lh','rh')})
 v=global_ref.subject_globals(**request)
 return {'subject':entry['subject_id'],'species':'rhesus' if nonhuman else 'human','scale_status':v['scale_status'],'scale_k':v['scale_k'],**v['physical'],**{'stored_'+k:x for k,x in v['stored'].items()}}

def table(rows,keys,columns):return {'rows':rows,'keys':keys,'columns':columns}
def prepare(batch):
 catalog=json.loads((batch/'catalog.e1.json').read_text());human=[x for x in catalog['roots'] if x['species_declared']=='human' and '/input_views/' not in x['path']];monkey=[x for x in catalog['roots'] if x['species_declared']=='rhesus']
 assert len(human)==20 and len(monkey)==6
 pp=catalog['participants_tables'][0]
 with Path(pp['path']).open(newline='') as f:participants={x[pp['id_column']]:x for x in csv.DictReader(f,delimiter='\t')}
 rows=[y for x in human for y in roi(Path(x['path']),x['subject_id'])];one=[x for x in rows if x['subject']=='IXI064'];assert len(one)==62 and len(rows)==1240,(len(one),len(rows))
 keys=['subject','hemisphere','metric','label_key','name'];cols=['vertex_count','mean','std_population','median','zero_count']
 reference={'S1':{'summary.csv':table(one,keys,cols)}}
 asym=copy.deepcopy(one);pairs={}
 for x in asym:pairs.setdefault(x['name'],{})[x['hemisphere']]=x['mean']
 for x in asym:
  v=pairs[x['name']];x['asymmetry_index']=2*(v['lh']-v['rh'])/(v['lh']+v['rh'])
 reference['S3']={'summary.csv':table(asym,keys,cols+['asymmetry_index'])}
 groupcols=['n','effect','estimate','se','t','df','p','q_fdr','effect_size','effect_size_kind','status'];gkeys=['hemisphere','metric','label_key','name']
 for case,terms in [('G1',[{'column':'age','kind':'continuous'},{'column':'sex','kind':'categorical','reference':'F'}]),('G2',[{'column':'sex','kind':'categorical','reference':'F'}])]:
  model=stats.regional_glm(rows,participants,terms);assert model['n_tests']==62
  reference[case]={'regional_values.csv':table(rows,keys,cols),'group_results.csv':table(model['rows'],gkeys,groupcols)}
 allglobal=[globals_(x) for x in human+monkey];oneglobal=[x for x in allglobal if x['subject']=='IXI064']
 reference['S2']={'global_metrics.csv':table(oneglobal,['subject','species'],METRICS+['scale_status','scale_k']+['stored_'+k for k in METRICS])}
 areas=[{'subject':x['subject'],'total_area_mm2':x['total_area_mm2'],'age':float(participants[x['subject']]['age'])} for x in allglobal if x['species']=='human']
 synthetic=[{'subject':x['subject'],'hemisphere':'both','metric':'total_area_mm2','label_key':0,'name':'whole_cortex','mean':x['total_area_mm2']} for x in areas]
 model=stats.regional_glm(synthetic,participants,[{'column':'age','kind':'continuous'}]);assert model['n_tests']==1
 g3=[{k:v for k,v in x.items() if k in groupcols} for x in model['rows']]
 reference['G3']={'global_area_values.csv':table(areas,['subject'],['total_area_mm2','age']),'group_results.csv':table(g3,['effect'],[k for k in groupcols if k not in ('effect','status')])}
 summary=global_ref.cross_species_summary([{'subject':x['subject'],'species':x['species'],'physical':{m:x[m] for m in METRICS}} for x in allglobal],numerator='human',denominator='rhesus')['summary']
 reference['X1']={'global_metrics.csv':table(allglobal,['subject','species'],METRICS),'species_summary.csv':table(summary,['metric'],['human_n','human_mean','rhesus_n','rhesus_mean','ratio'])}
 sources={str(p):sha(p) for e in human+monkey for d in ('label','surf','stats','mri') for p in (Path(e['path'])/d).glob('*') if p.is_file() and (p.name.endswith(('.thickness','.annot','.label','.pial','.white','.stats')) or p.name=='brainmask.mgz')}
 save(batch/'host_reference_private.json',{'references':reference,'source_sha256':sources,'tolerances':{'atol':ATOL,'rtol':RTOL},'model_calls':0,'not_agent_mount':True})
 save(batch/'host_reference_preflight.json',{'ready':True,'cases':{k:{f:len(t['rows']) for f,t in v.items()} for k,v in reference.items()},'numeric_tolerances_unchanged':True,'source_hashes_count':len(sources),'private_reference_sha256':sha(batch/'host_reference_private.json'),'model_calls':0})
 print(json.dumps({'reference_preflight':'pass','case_count':len(reference),'model_calls':0}))

def compare(t,rows):
 expected=copy.deepcopy(t['rows']);columns=t['columns']
 # Equivalent two-level coding: accept the reverse contrast only when ALL signed statistics reverse consistently.
 if expected and rows and 'effect' in expected[0] and expected[0]['effect']=='sex[M]' and all(r.get('effect')=='sex[F]' for r in rows):
  for r in expected:
   r['effect']='sex[F]'
   for k in ('estimate','t','effect_size'):
    if r.get(k) is not None:r[k]=-r[k]
 return independent.compare_rows(expected,rows,t['keys'],columns)

def load_csv(path):
 if path.is_symlink() or not path.is_file():raise ValueError('Missing or linked output')
 if path.stat().st_size>20*1024*1024:raise ValueError('Output size limit')
 with path.open(encoding='utf-8-sig',newline='') as stream:
  rd=csv.DictReader(stream)
  if not rd.fieldnames or len(set(rd.fieldnames))!=len(rd.fieldnames):raise ValueError('Invalid CSV header')
  rows=list(rd)
 if any(None in x for x in rows):raise ValueError('CSV shape error')
 return rows

def fixtures(batch):
 ref=json.loads((batch/'host_reference_private.json').read_text())['references'];tests=[]
 t=ref['S1']['summary.csv']
 for name,rows,want in [('correct',copy.deepcopy(t['rows']),'pass'),('valid_reordered_extra',list(reversed([dict(x,comment='alternate') for x in t['rows']])),'pass'),('wrong_value',copy.deepcopy(t['rows']),'fail'),('shortcut_one_row',copy.deepcopy(t['rows'][:1]),'fail'),('duplicate',copy.deepcopy(t['rows'])+[t['rows'][0]],'error'),('missing_metric',copy.deepcopy(t['rows']),'fail')]:
  if name=='wrong_value':rows[0]['mean']+=.01
  if name=='missing_metric':rows[0].pop('mean')
  try:actual=compare(t,rows)['status']
  except ValueError:actual='error'
  assert actual==want,(name,actual,want);tests.append({'fixture':name,'expected':want,'actual':actual})
 g=ref['G2']['group_results.csv'];reverse=copy.deepcopy(g['rows'])
 for x in reverse:
  x['effect']='sex[F]'
  for k in ('estimate','t','effect_size'):x[k]=-x[k]
 assert compare(g,reverse)['status']=='pass';tests.append({'fixture':'valid_reverse_group_contrast','actual':'pass','expected':'pass'})
 fixture=batch/'verifier_fixtures';fixture.mkdir(exist_ok=True)
 for name,data in [('corrupt.csv','a,a\n1,2\n'),('missing.csv',None)]:
  f=fixture/name
  if data is not None:f.write_text(data)
  try:load_csv(f);raise AssertionError('Invalid evidence accepted')
  except ValueError:tests.append({'fixture':name,'actual':'error','expected':'error'})
 save(batch/'verifier_fixtures.json',{'status':'pass','tests':tests,'unchanged_atol':ATOL,'unchanged_rtol':RTOL,'hidden_reference_outside_inputs':all('/work/' not in str(p) for p in [batch/'host_reference_private.json']),'model_calls':0})
 print(json.dumps({'verifier_fixtures':'pass','count':len(tests)}))

def grade(batch,case):
 folder=batch/('case_'+case);summary=json.loads((folder/'summary.json').read_text());spec=json.loads((batch/'cases.host.json').read_text())[case]['spec'];key=spec['host_verifier']['case']
 answer=json.loads((folder/'agent_response.json').read_text());metadata=answer.get('metadata') or {};output=metadata.get('output_directory');reference=json.loads((batch/'host_reference_private.json').read_text())['references'];tables={}
 if key in reference:
  for filename,t in reference[key].items():
   try:
    if not output:raise ValueError('No output directory returned')
    p=Path(output)/filename;comp=compare(t,load_csv(p));tables[filename]={k:v for k,v in comp.items() if k!='differences'};tables[filename].update(output_sha256=sha(p),source='independent E1 fixed-scope reference')
   except Exception as exc:tables[filename]={'status':'missing_or_invalid','error_type':type(exc).__name__}
 public=(metadata.get('validation') or {}).get('public_output_contract') or {};card=metadata.get('conclusion_card') or {}
 native=summary.get('full_chain_passed',False)
 result={'case':case,'task_id':spec['task_id'],'tables':tables,'fixed_scope_numeric_pass':bool(tables) and all(t['status']=='pass' for t in tables.values()),'native_full_chain_pass':native,'conclusion_card_status':card.get('overall_status'),'native_public_contract':public.get('status'),'correct_refusal':None if key.startswith('N') else 'not_applicable','semantic_audit':'required for refusal, scope/conclusion interpretation; no model judge called','full_original_task_pass':native and bool(tables) and all(t['status']=='pass' for t in tables.values()),'source_commit':summary.get('source_commit')}
 save(folder/'host_grade.json',result)
 # No reference values, per-subject rows, generated code, raw provider messages or user tokens in this projection.
 print(json.dumps({'case':case,'table_statuses':{k:v['status'] for k,v in tables.items()},'native_full_chain_pass':native}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','fixtures','grade']);p.add_argument('--batch',type=Path,required=True);p.add_argument('--case');a=p.parse_args()
 {'prepare':lambda:prepare(a.batch),'fixtures':lambda:fixtures(a.batch),'grade':lambda:grade(a.batch,a.case)}[a.action]()
