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
    return obj,sha


def source_read(source_id,start,max_chars):
    if not isinstance(source_id,str) or not source_id.startswith('METHOD_SOURCE_group_'):
        return None
    if type(start)is not int or start<0 or type(max_chars)is not int or not 100<=max_chars<=12000:
        raise ValueError('Bounded source cursor required')
    body,sha=overlay()
    source=next((s for s in body['sources'] if 'METHOD_SOURCE_'+s['id']==source_id),None)
    if source is None:raise ValueError('Unknown registered original parent ID')
    text=source['text']
    return {'status':'ok','id':source_id,'text':text[start:start+max_chars],'url':source['url'],
            'heading':'V14 project implementation note; not original source full text',
            'text_sha256':source['text_sha256'],'release_sha256':sha,'retrieval_provider_http_calls':0}
