"""Operator-declared participant tables, separate from subject root grants."""
from pathlib import Path
import hashlib,json,os

MAX_TABLE_BYTES = 8 * 1024 * 1024


def register_tables(tools):
    tools.participants_tables = []
    location = os.environ.get('AGENT_DATA_CATALOG')
    if not location:
        return
    catalog = Path(location)
    if catalog.is_symlink():
        raise ValueError('Data catalogue must not be a symlink')
    body = json.loads(catalog.read_text(encoding='utf-8'))
    tables = body.get('participants_tables', [])
    if not isinstance(tables,list) or len(tables)>16:
        raise ValueError('participants_tables must contain at most 16 declarations')
    datasets={row.get('dataset') for row in body.get('roots',[]) if Path(row['path']).resolve() in tools.input_roots}
    for declaration in tables:
        if not isinstance(declaration,dict) or any(not isinstance(declaration.get(k),str) or not declaration[k].strip() for k in ('dataset','path','id_column','source','license')):
            raise ValueError('participants_tables requires dataset/path/id_column/source/license strings')
        if declaration['dataset'] not in datasets:
            continue
        source=Path(declaration['path']).absolute()
        if source.suffix.lower() not in ('.tsv','.csv') or any(p.is_symlink() for p in (source,*source.parents)) or not source.is_file() or source.stat().st_size>MAX_TABLE_BYTES:
            raise ValueError('Participant table must be a bounded regular TSV/CSV without symlink components')
        raw=source.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        stage=tools.control_store.root/'participant_inputs'/sha
        stage.mkdir(parents=True,exist_ok=True)
        snapshot=stage/source.name
        if not snapshot.exists():
            snapshot.write_bytes(raw);snapshot.chmod(0o400)
        if hashlib.sha256(snapshot.read_bytes()).hexdigest()!=sha:
            raise ValueError('Participant snapshot changed')
        index=len(tools.input_roots);tools.input_roots.append(stage)
        tools.participants_tables.append({**declaration,'index':index,'mapped_path':f'/inputs/{index}/{source.name}','sha256':sha})
    tools.data.input_roots=list(tools.input_roots)
    tools.data.roots=list(dict.fromkeys([tools.data.workdir,*tools.input_roots]))
    if hasattr(tools.executor,'input_roots'):
        tools.executor.input_roots=list(tools.input_roots)


def table_paths(tools, entries):
    datasets={entry.get('dataset') for entry in entries}
    return [row['mapped_path'] for row in getattr(tools,'participants_tables',[]) if row['dataset'] in datasets]
