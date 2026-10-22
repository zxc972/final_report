"""Compact public group execution instructions and explicit input manifest."""
import hashlib,json
from .analysis_control_store import canonical


def write_manifest(tools,plan,bundle):
    from .analysis_agent import _write_regular
    scope=plan['analysis_scope']
    groups={}
    for call in bundle['operations']['calls']:
        if call['function']!='parcel_summary':continue
        subject,hemi=call['scope'].rsplit('/',1)
        groups.setdefault(subject,[]).append({'hemisphere':hemi,**call['inputs'],'label_sets_ref':bundle['label_sets_ref']['path']})
    manifest={'schema':'primatex.group_inputs.v1','subjects':groups,'subject_count':len(groups),
              **{k:scope[k] for k in ('design','design_terms','participants_table','effect','included_subjects','excluded_subjects','site_scanner_composition','d_min','power_assumptions')},
              'label_sets_ref':bundle['label_sets_ref'], 'tables':bundle['output_contract'].get('tables',{})}
    raw=canonical(manifest)
    _write_regular(tools.resolve('/work/inputs_manifest.json',writable=True),tools.workdir,raw.decode())
    return {'path':'/work/inputs_manifest.json','sha256':hashlib.sha256(raw).hexdigest(),'subject_count':len(groups)}


def card(plan,bundle):
    scope=plan['analysis_scope'];design=json.dumps(scope['design'],ensure_ascii=False,separators=(',',':'))
    if len(design)>400:design='inputs_manifest.json[design]; effect='+scope['effect']
    regional='subject,hemisphere,metric,label_key,name,vertex_count,mean,std_population,median,zero_count,units'
    group='hemisphere,metric,label_key,name,n,effect,estimate,se,t,df,p,q_fdr,effect_size,effect_size_kind,status'
    lines=['import primatex_ops as ops; numpy/scipy available.',
      f"Inputs: /work/inputs_manifest.json; subjects={len(plan['data']['subjects'])}; design={design}",
      'Read manifest subjects, design_terms, participants_table, label_sets_ref; each subject entry binds metric_path/annotation_path/mask_path/label_set_scope.',
      'Use ops.parcel_summary(metric,labels,group.labels,mask=cortex), then OLS(intercept+design_terms), two-sided t.',
      'regional_values.csv: '+regional,
      'group_results.csv: '+group,
      'Exact columns/identities/names; no aliases. Group identity=hemisphere,metric,label_key. One row per retained partition, including skipped:<reason>; skipped statistics empty, fitted status=ok.',
      'effect='+scope['effect']+'; categorical uses column[level]. BH q_fdr over ALL fitted partitions, both hemispheres/all metrics together.',
      'Effect size: pooled Cohen d for unadjusted factor; Pearson r for unadjusted continuous; otherwise partial_r=t/sqrt(t*t+df).',
      'CSV repr/%.17g. summary.json: methods,limitations. report.md: n/exclusions,FDR family,effect size,d_min,site/scanner (or unavailable),stored units/scale limits.',
      'Code: '+plan['code_path']+'; write_code then run_python(); automatic checks and review.']
    text='\n'.join(lines)
    if len(text)>1500:raise ValueError('Group execution card exceeds 1500 characters; shorten design names')
    return text
