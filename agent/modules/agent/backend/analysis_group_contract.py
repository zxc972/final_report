"""Public group table schema and deterministic regional identities."""
GROUP_TYPES={'hemisphere':'str','metric':'str','label_key':'int','name':'str','n':'int','effect':'str','estimate':'float','se':'float','t':'float','df':'int','p':'float','q_fdr':'float','effect_size':'float','effect_size_kind':'str','status':'str'}
STAT_COLUMNS=('n','estimate','se','t','df','p','q_fdr','effect_size','effect_size_kind')


def group_contract(plan,regional):
    expected={}
    for row in regional['expected_identities']:
        key=tuple(row[k] for k in ('hemisphere','metric','label_key'))
        value={k:row[k] for k in ('hemisphere','metric','label_key','name')}
        if key in expected and expected[key]!=value:raise ValueError('Atlas label names differ across subjects')
        expected[key]=value
    return {'schema':'primatex.group_table_contract.v1','columns':dict(GROUP_TYPES),'identity_columns':['hemisphere','metric','label_key'],
      'allowed_values':{**{k:sorted({r[k] for r in expected.values()},key=str) for k in ('hemisphere','metric')},'effect':[plan['analysis_scope']['effect']]},
      'expected_rows':len(expected),'expected_identities':list(expected.values()),'fixed_values':{'effect':plan['analysis_scope']['effect']},
      'nullable_columns':list(STAT_COLUMNS),'extra_columns_allowed':False,'alias_mapping':False,
      'design_columns':plan['analysis_scope']['design_columns'],
      'row_rule':'One row for every retained hemisphere/metric/label_key, including skipped:<reason>; empty statistics for skips; BH across all fitted regions of both hemispheres and selected metrics'}


def row_errors(row,contract):
    status=row.get('status','');errors=[]
    if status.startswith('skipped:') and status[8:].strip():
        if any(str(row.get(c,'')).strip() for c in STAT_COLUMNS):errors.append('skipped rows require empty statistics')
    elif status=='ok':
        if any(not str(row.get(c,'')).strip() for c in STAT_COLUMNS):errors.append('fitted rows require all statistics and effect_size_kind')
        try:
            if int(row['n'])-contract['design_columns']!=int(row['df']) or int(row['df'])<1:errors.append('n/df do not match sealed design')
            if float(row['se'])<=0 or any(not 0<=float(row[c])<=1 for c in ('p','q_fdr')):errors.append('invalid se/p/q_fdr range')
            if row['effect_size_kind'] not in {'cohens_d','pearson_r','partial_r'}:errors.append('unknown effect_size_kind')
        except (KeyError,ValueError,TypeError):errors.append('invalid fitted statistics')
    else:errors.append('status must be ok or skipped:<nonempty reason>')
    return errors
