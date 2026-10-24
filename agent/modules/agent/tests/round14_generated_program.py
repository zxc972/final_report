"""Offline fake coder's complete numpy/scipy program; no host reference imports."""
import csv,json,math
from pathlib import Path
import numpy as np
from scipy import stats
import primatex_ops as ops

manifest=json.loads(Path('/work/inputs_manifest.json').read_text())
bundle=json.loads(Path('/work/execution_bundle.v000001.json').read_text())
label_sets=json.loads(Path(manifest['label_sets_ref']['path']).read_text())
regional=[]
for subject,bindings in manifest['subjects'].items():
    for binding in bindings:
        labels,names,ctab=ops.read_annotation(binding['annotation_path'])
        metric=ops.read_surface_metric(binding['metric_path'])
        mask=ops.read_label(binding['mask_path'])
        scope=binding['label_set_scope'];group=label_sets[scope]
        for row in ops.parcel_summary(metric,labels,group['labels'],mask=mask):
            regional.append({'subject':subject,'hemisphere':binding['hemisphere'],'metric':Path(binding['metric_path']).suffix[1:],'units':'stored; software convention mm',**row})
with Path(manifest['participants_table']['path']).open() as stream:
    people={r[manifest['participants_table']['id_column']]:r for r in csv.DictReader(stream,delimiter='\t' if manifest['participants_table']['path'].endswith('.tsv') else ',')}
regions={}
for row in regional:
    key=(row['hemisphere'],row['metric'],row['label_key'],row['name']);regions.setdefault(key,{})[row['subject']]=row['mean']
results=[]
for key,values in sorted(regions.items()):
    subjects=[s for s in manifest['included_subjects'] if s in values]
    y=np.array([values[s] for s in subjects],dtype=float)
    columns=[np.ones(len(subjects))]
    effect_values=None
    for i,term in enumerate(manifest['design_terms']):
        data=[people[s][term['column']] for s in subjects]
        if term['kind']=='continuous':
            data=np.asarray(data,dtype=float);columns.append(data-data.mean())
        else:
            levels=sorted(set(data));reference=term.get('reference',levels[0]);others=[v for v in levels if v!=reference]
            columns.extend(np.array([v==level for v in data],dtype=float) for level in others)
        if i==0:effect_values=data
    X=np.column_stack(columns)
    row={k:'' for k in bundle['output_contract']['tables']['group_results.csv']['columns']}
    row.update(hemisphere=key[0],metric=key[1],label_key=key[2],name=key[3],effect=manifest['effect'])
    try:
        beta,_,rank,_=np.linalg.lstsq(X,y,rcond=None)
        if rank<X.shape[1] or len(y)<=X.shape[1]:raise ValueError('rank_deficient')
        residual=y-X@beta;df=len(y)-X.shape[1];se=float(np.sqrt(np.dot(residual,residual)/df*np.linalg.inv(X.T@X)[1,1]))
        if not se>0 or np.ptp(y)==0:raise ValueError('zero_variance_or_nonfinite_test')
        t=float(beta[1]/se);p=float(2*stats.t.sf(abs(t),df))
        if len(manifest['design_terms'])==1 and manifest['design_terms'][0]['kind']=='categorical':
            treatment=manifest['effect'].split('[',1)[1][:-1];a=y[np.array([v==treatment for v in effect_values])];b=y[np.array([v!=treatment for v in effect_values])]
            pooled=((len(a)-1)*a.var(ddof=1)+(len(b)-1)*b.var(ddof=1))/(len(a)+len(b)-2)
            size=float((a.mean()-b.mean())/np.sqrt(pooled));kind='cohens_d'
        elif len(manifest['design_terms'])==1:
            size=float(stats.pearsonr(np.asarray(effect_values,dtype=float),y).statistic);kind='pearson_r'
        else:size=t/math.sqrt(t*t+df);kind='partial_r'
        row.update(n=len(y),estimate=float(beta[1]),se=se,t=t,df=df,p=p,effect_size=size,effect_size_kind=kind,status='ok')
    except (ValueError,np.linalg.LinAlgError) as exc:
        row['status']='skipped:'+str(exc)
    results.append(row)
fitted=[r for r in results if r['status']=='ok'];order=sorted(range(len(fitted)),key=lambda i:fitted[i]['p']);previous=1.
for rank in range(len(order),0,-1):
    i=order[rank-1];previous=min(previous,fitted[i]['p']*len(order)/rank);fitted[i]['q_fdr']=previous
for filename,rows in [('regional_values.csv',regional),('group_results.csv',results)]:
    with Path('/work',filename).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=bundle['output_contract']['tables'][filename]['columns'],extrasaction='ignore');writer.writeheader();writer.writerows(rows)
Path('/work/summary.json').write_text(json.dumps({'methods':'numpy/scipy additive regional GLM with intercept; both hemispheres BH','limitations':'Synthetic only; normal-approximation power; no expert QC'}))
Path('/work/report.md').write_text('Sample size n='+str(len(manifest['included_subjects']))+'\nExcluded subjects: '+json.dumps(manifest['excluded_subjects'])+'\nFDR family: ALL fitted partitions of both hemispheres and all selected metrics; BH.\nEffect size: Cohen d / Pearson r / adjusted partial_r.\nd_min='+str(manifest['d_min'])+'; '+manifest['power_assumptions']+'\nSite/scanner composition: '+json.dumps(manifest['site_scanner_composition'])+'\nStored values, software convention mm; physical scale/history unverified; rescale no; plan version 1; synthetic data only.')
