"""Observed serialization diagnostics only; no contract decision or repair."""
import csv,io,json

def inspect_bytes(raw):
    sample=raw[:32768].decode('utf-8-sig',errors='replace')
    detected=None
    try:detected=csv.Sniffer().sniff(sample,delimiters=',;\t|').delimiter
    except csv.Error:
        first=sample.splitlines()[0] if sample.splitlines() else ''
        counts={d:first.count(d) for d in ',;\t|'}
        if max(counts.values(),default=0):detected=max(counts,key=counts.get)
    def header(delimiter):
        try:return [str(c)[:160] for c in next(csv.reader(io.StringIO(sample),delimiter=delimiter),[])[:12]]
        except csv.Error:return []
    return {'actual_reader_delimiter':',','observed_header':header(','),
            'detected_delimiter':detected,'detected_header':header(detected) if detected else [],
            'diagnostic_only':True,'no_alias_mapping_or_reparse_for_validation':True}

def describe(info):
    return 'Observed CSV header (first 12): '+json.dumps(info['observed_header'],ensure_ascii=False)+'; detected delimiter='+repr(info['detected_delimiter'])+'; required parser delimiter=comma'

def outputs(tools):
    saved=tools.control_store.latest('execution_bundle') if tools.control_store else None
    if not saved:return []
    names=[p if isinstance(p,str) else p['path'] for p in saved['record']['output_contract']['files']]
    found=[]
    for name in names:
        if not name.endswith('.csv'):continue
        path=tools.resolve('/work/'+name.removeprefix('/work/'))
        if path.is_file() and not path.is_symlink():
            with path.open('rb') as stream:info=inspect_bytes(stream.read(32768))
            found.append({'file':name,'exists':True,**info})
        else:found.append({'file':name,'exists':False,'observed_header':None,'detected_delimiter':None})
    observed=[]
    for p in sorted(tools.workdir.glob('*.csv'))[:8]:
        if p.is_file() and not p.is_symlink():
            with p.open('rb') as stream:observed.append({'file':p.name,**inspect_bytes(stream.read(32768))})
    return {'sealed_tables':found,'observed_csv_files':observed,'diagnostic_only':True}
