"""Design binding from the registered, fingerprinted participant table."""
import csv,math
from statistics import NormalDist
from .analysis_group_stats import build_design, DesignError, _invert
from .analysis_template_bindings import unwrap


def participants(tools, scope):
    path=tools.resolve(scope['participants_table']['path'])
    import hashlib
    if hashlib.sha256(path.read_bytes()).hexdigest()!=scope['participants_table']['sha256']:
        raise ValueError('Participant table fingerprint changed')
    with path.open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream,delimiter='\t' if path.suffix.lower()=='.tsv' else ','))
    id_column=scope['participants_table']['id_column']
    ids=[row.get(id_column,'').strip() for row in rows]
    if len(ids)!=len(set(ids)) or any(not s for s in ids):
        raise DesignError('Participant IDs must be present and unique')
    return dict(zip(ids,rows))


def bind_design(tools, intent, entries, files):
    tables=[unwrap(f) for f in files if unwrap(f).get('format') in {'tsv','csv'}]
    available=[{'path':t['path'],'columns':(t.get('table') or {}).get('columns',[])} for t in tables]
    def error(reason,field='design'):
        return None, {'status':'needs_design','reason':reason,'field_errors':[{'field':field,'message':reason}], 'available_columns':available,'candidates':[]}
    if intent.design is None:
        return error('design is required for group/correlation; select effect and covariates from available_columns')
    datasets={e.get('dataset') for e in entries}; species={e.get('species_declared') for e in entries}
    if len(entries)>128 or len(datasets)!=1 or None in datasets or len(species)!=1 or None in species:
        return error('Group subjects must have one registered dataset and species, at most 128')
    if len(tables)!=1:
        return error('Exactly one registered participant table for the selected dataset is required')
    table=tables[0];meta=table['table'];d=intent.design.model_dump()
    columns=[d['effect'],*d['covariates']]
    missing=[c for c in columns if c not in meta['columns']]
    if missing:return error('Missing design columns: '+','.join(missing))
    terms=[{'column':c,'kind':'continuous' if meta['column_types'][c]=='numeric' else 'categorical'} for c in columns]
    if d['reference'] is not None:
        if terms[0]['kind']!='categorical':return error('reference requires a categorical effect','design.reference')
        terms[0]['reference']=d['reference']
    scope={'design':d,'design_terms':terms,'participants_table':{'path':table['path'],'id_column':meta['id_column'],'sha256':table['sha256']}}
    try:
        cohort=participants(tools,scope)
        design=build_design(cohort,[e['subject_id'] for e in entries],terms)
        if len(design['effect_columns'])!=1:raise DesignError('Effect must be numeric or a two-level factor')
        groups={'all':design['subjects']}
        if terms[0]['kind']=='categorical':
            levels=design['levels'][d['effect']]['levels']
            groups={level:[s for s in design['subjects'] if cohort[s][d['effect']].strip()==level] for level in levels}
            if min(map(len,groups.values()),default=0)<2:raise DesignError('Each effect level requires at least 2 subjects')
        n=len(design['subjects']);p=len(design['columns'])
        if n<=p:raise DesignError('Positive residual degrees of freedom required')
        x=design['X'];inverse=_invert([[math.fsum(r[i]*r[j] for r in x) for j in range(p)] for i in range(p)])
        effect_index=design['columns'].index(design['effect_columns'][0])
        effect_scale=1.0
        if terms[0]['kind']=='continuous':
            values=[float(cohort[s][d['effect']]) for s in design['subjects']];mean=math.fsum(values)/n
            effect_scale=math.sqrt(math.fsum((v-mean)**2 for v in values)/(n-1))
        d_min=(NormalDist().inv_cdf(.975)+NormalDist().inv_cdf(.8))*math.sqrt(inverse[effect_index][effect_index])*effect_scale
    except (DesignError,ValueError,KeyError) as exc:return error(str(exc))
    composition={c:{v:sum(cohort[s].get(c)==v for s in design['subjects']) for v in sorted({cohort[s].get(c,'') for s in design['subjects']})} for c in meta['columns'] if c.lower() in {'site','scanner','site_id','scanner_id','manufacturer'}}
    scope.update(groups=groups,design_columns=p,effect=design['effect_columns'][0],excluded_subjects=design['excluded'],included_subjects=design['subjects'],n=n,df=n-p,d_min=d_min,site_scanner_composition=composition,
        power_assumptions='Normal approximation, two-sided alpha=.05, power=.8; design covariance includes nuisance terms; standardized slope for continuous effect, residual-SD units for factor; not FDR-adjusted power')
    return scope,None
