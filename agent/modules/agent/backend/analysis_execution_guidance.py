"""Small cards and sealed, read-only schema documentation; no analysis code."""
from __future__ import annotations
import hashlib,json
from pathlib import PurePosixPath
GUIDE='/work/INPUTS.md'
TABLES='/work/contract_tables.json'

def compact_card(plan,bundle):
    method=plan['method']['method_id'];group=method=='method:v14:group_regional_glm';glob=method=='method:v15:global_morphometry'
    outputs=[v if isinstance(v,str) else v['path'] for v in bundle['output_contract']['files']]
    lines=['import primatex_ops as ops',
           'Read '+GUIDE+' for input structures, exact reader returns, method rules and disclosures.',
           'Sealed table schema: '+TABLES+'; use exact names/identities from the full bundle.',
           'Optional writer: ops.write_contract_table(table_name, rows) writes the sealed filename/columns/order as UTF-8 comma CSV with header and no index.',
           'Code: '+plan['code_path'],'Outputs: '+','.join(outputs),
           'JSON: methods,limitations. CSV repr/%.17g; JSON native floats. Do not round stored results.',
           'Full plan and bindings: '+bundle.get('bundle_ref','sealed execution_bundle JSON'),
           'Write the complete analysis program; run_python(); automatic contract checks and review.']
    if group:lines.insert(3,'Inputs: /work/inputs_manifest.json; ops.read_group_inputs(path) returns raw row dicts with values, not regional statistics; compute the requested model yourself.')
    if glob:
        lines.insert(3,'Global method: use the species-specific formulas, scale policy and missing-value rules in INPUTS.md; descriptive n=1.')
        lines.insert(4,'Macaque direct volume/area/thickness; no aseg/annot.' if plan.get('analysis_scope',{}).get('global_species_policy',{}).get('variant')=='macaque_direct_native' else 'Human global normalization: BrainSegVol/eTIV; retain missing-value rules.')
    if bundle.get('asymmetry_contract'):lines.insert(3,'AI: pair same subject/metric/name; 2*(L-R)/(L+R), undefined at L+R=0; retain signed value in both rows; descriptive n=1.')
    text='\n'.join(lines);limit=1500 if group or glob else 2200
    if len(text)>limit:
        from .analysis_system_defects import SystemDefect
        raise SystemDefect('execution_card_length','Host-generated execution card exceeds its bound',length=len(text),limit=limit,method=method)
    return text

def compact_payload(payload):
    return {'status':'committed','version':payload['version'],'execution_card':compact_card(payload['plan'],payload['execution_bundle']),'state':payload.get('state')}

def serialization_tables(bundle):
    contract=bundle['output_contract'];tables={}
    for item in contract['files']:
        name=item if isinstance(item,str) else item['path']
        if not name.endswith('.csv'):continue
        spec=contract.get('tables',{}).get(name) or contract.get('table')
        columns=list(spec['columns']) if spec else list(contract.get('csv_columns',[]))
        tables[name]={'columns':columns}
    return {'schema':'primatex.contract_serialization.v1','tables':tables,'encoding':'utf-8','delimiter':',','header':True,'index':False,'precision':'repr/17 significant digits; None is empty; no aliases or numeric repairs'}

def write_documents(tools,plan,bundle,version):
    from .analysis_agent import _write_regular
    from .analysis_execution_card import detailed_instructions
    payload={'plan':plan,'execution_bundle':bundle,'version':version}
    text=('# Sealed input and output guide\n\n'
          'Use the registered raw inputs and write the complete scientific analysis program.\n'
          'ops.write_contract_table(table_name, rows) is an optional serializer only; it computes no statistics.\n'
          'Rows are dicts; all sealed columns must be present. None writes an empty cell. Extra keys are not written.\n'
          'Canonical table names and column order: /work/contract_tables.json. Full identities remain in the execution bundle.\n\n'
          +detailed_instructions(payload)+'\n\nAll observations and required disclosures:\n'
          +json.dumps(bundle.get('must_disclose',[]),ensure_ascii=False,indent=2)+'\n')
    docs={GUIDE:text,TABLES:json.dumps(serialization_tables(bundle),ensure_ascii=False,indent=2)+'\n'}
    refs=[]
    for name,content in docs.items():
        _write_regular(tools.resolve(name,writable=True),tools.workdir,content)
        refs.append({'path':name,'sha256':hashlib.sha256(content.encode('utf-8')).hexdigest()})
    return refs

def verify_documents(tools,bundle):
    for ref in bundle.get('execution_documents',[]):
        path=tools.resolve(ref['path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=ref['sha256']:
            return False
    return True

def read_document_allowed(tools,arguments):
    saved=tools.control_store.latest('execution_bundle')
    if not saved:return False
    record=saved['record']
    names={r['path'] for r in record.get('execution_documents',[])}
    names.add(record.get('bundle_ref'))
    for key in ('label_sets_ref','inputs_manifest'):
        names.add(record.get(key,{}).get('path'))
    return arguments.get('path') in names - {None}
