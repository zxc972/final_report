"""Read-only, SHA-bound v14 overlay; the v13 release remains immutable."""
import hashlib,json
from pathlib import Path


def overlay():
    p=Path(__file__).resolve().parent.parent/'knowledge_analysis/method_graph_overlay_v14.json'
    raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if p.is_symlink() or sha!=p.with_suffix('.sha256').read_text().strip():
        raise ValueError('Method overlay digest mismatch')
    obj=json.loads(raw)
    if obj.get('schema')!='primatex.method_graph.v1' or [m['id'] for m in obj['methods']]!=['method:v14:group_regional_glm']:
        raise ValueError('Invalid v14 method overlay')
    p15 = p.with_name('method_graph_overlay_v15.json')
    raw15 = p15.read_bytes()
    sha15 = hashlib.sha256(raw15).hexdigest()
    if p15.is_symlink() or sha15 != p15.with_suffix('.sha256').read_text().strip():
        raise ValueError('V15 method overlay digest mismatch')
    extra = json.loads(raw15)
    if [m['id'] for m in extra['methods']] != ['method:v15:global_morphometry']:
        raise ValueError('Invalid v15 method overlay')
    for key in ('methods', 'nodes', 'edges', 'sources'):
        obj[key].extend(extra[key])
    return obj,hashlib.sha256((sha+sha15).encode()).hexdigest()


def source_read(source_id,start,max_chars):
    if not isinstance(source_id,str) or not source_id.startswith(('METHOD_SOURCE_group_', 'METHOD_SOURCE_global_')):
        return None
    if type(start)is not int or start<0 or type(max_chars)is not int or not 100<=max_chars<=12000:
        raise ValueError('Bounded source cursor required')
    body,sha=overlay()
    source=next((s for s in body['sources'] if 'METHOD_SOURCE_'+s['id']==source_id),None)
    if source is None:raise ValueError('Unknown registered original parent ID')
    text=source['text']
    return {'status':'ok','id':source_id,'text':text[start:start+max_chars],'url':source['url'],
            'heading':'Project implementation note; not original source full text',
            'text_sha256':source['text_sha256'],'release_sha256':sha,'retrieval_provider_http_calls':0}
