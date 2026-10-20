"""Server-pinned default candidate knowledge release; credentials never live here."""
from pathlib import Path
import hashlib,json,os,re,stat
DEFAULT_MANIFEST=Path(__file__).resolve().parent.parent/'knowledge_analysis'/'research_release.json'
def configured_research_root(manifest_path:Path|None=None)->Path|None:
    key='AGENT_RESEARCH_EVIDENCE_ROOT'
    if key in os.environ:
        value=os.environ[key].strip()
        return Path(value)if value else None
    manifest=Path(manifest_path)if manifest_path is not None else DEFAULT_MANIFEST
    if not manifest.exists():return None
    if manifest.is_symlink()or not stat.S_ISREG(manifest.lstat().st_mode)or manifest.stat().st_size>4096:
        raise ValueError('Invalid server knowledge release manifest')
    obj=json.loads(manifest.read_text())
    if obj.get('schema')!='primatex.research_release_pointer.v1':raise ValueError('Unknown release pointer schema')
    root=Path(obj['root']);expected=obj.get('config_sha256','')
    if not root.is_absolute()or root.is_symlink()or not re.fullmatch('[a-f0-9]{64}',expected):raise ValueError('Invalid pinned research root')
    config=root/'config.json'
    if config.is_symlink()or not config.is_file()or config.stat().st_size>2*1024*1024:raise ValueError('Pinned release config unavailable')
    if hashlib.sha256(config.read_bytes()).hexdigest()!=expected:raise ValueError('Pinned release config digest mismatch')
    return root

