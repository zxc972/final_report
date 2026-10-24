"""Compact public group execution instructions and explicit input manifest."""
import hashlib,json
from pathlib import Path
from .analysis_control_store import canonical


def write_manifest(tools,plan,bundle):
    from .analysis_agent import _write_regular
    scope=plan['analysis_scope']
    groups={}
    for call in bundle['operations']['calls']:
        if call['function']!='parcel_summary':continue
        subject,hemi=call['scope'].rsplit('/',1)
        groups.setdefault(subject,[]).append({'hemisphere':hemi,'metric':Path(call['inputs']['metric_path']).name.split('.',1)[-1],**call['inputs'],'label_sets_ref':bundle['label_sets_ref']['path']})
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
    lines=[
      f"Inputs: /work/inputs_manifest.json; subjects={len(plan['data']['subjects'])}; design={design}",
      'Structure: manifest=dict; subjects=dict[ID -> list[dict]]; bindings=hemisphere,metric,metric_path,annotation_path,mask_path,label_set_scope.',
      'label_sets_ref.path: dict[scope -> dict]; labels: list[{key:int,name:str}]; key becomes row.label_key. Exact columns/values: manifest.tables.',
      'primatex_ops.read_group_inputs(manifest_path): readonly raw rows sorted by (subject,hemisphere,metric,label_key), plus name,values. No statistics; join participants by ID.',
      'primatex_ops.fdr_bh_by_identity(pvalues): {(hemisphere,metric,label_key):p/None} -> same keys:q/None; never name/position.',
      'Compute unweighted regional means/population SD; OLS intercept+design_terms, two-sided t. Exact table identities/names, include skipped:<reason> with empty statistics, fitted status=ok.',
      'effect='+scope['effect']+'; categorical column[level]. BH family: ALL fitted partitions across both hemispheres/all metrics.',
      'Effect size: pooled Cohen d for unadjusted factor; Pearson r for unadjusted continuous; otherwise partial_r=t/sqrt(t*t+df).',
      'CSV repr/%.17g; summary.json methods,limitations; report.md n/exclusions,FDR,effect size,d_min,site/scanner,stored units/scale limits.',
      'Code: '+plan['code_path']+'; write_code then run_python(); automatic checks and review.']
    text='\n'.join(lines)
    if len(text)>1500:raise ValueError('Group execution card exceeds 1500 characters; shorten design names')
    return text
