"""Read-only evidence worker: native frozen LightRAG + lexical parents + source graph.
No credentials, network LLM, indexing, or generated-code execution is permitted.
"""
import os,sys,pathlib,json,re,math,collections,hashlib,asyncio,logging
ROOT=pathlib.Path(__file__).resolve().parent
os.environ.update(HF_HUB_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='2',TIKTOKEN_CACHE_DIR='/data/xuancheng/retrieval_pilot_20261020/tokenizer_cache')
logging.basicConfig(level=logging.ERROR)
def read_json(name,max_bytes=24*1024*1024):
 p=ROOT/name
 if p.is_symlink() or not p.is_file() or p.stat().st_size>max_bytes:raise ValueError('Invalid registered evidence file')
 return json.loads(p.read_text())
def tokens(text):
 base=re.findall(r'[a-z][a-z0-9_]*|\d+',text.lower());return base+[part for word in base if '_' in word for part in word.split('_') if part]
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def snippet(text,query,cap=1400):
 ts=set(tokens(query));starts=[m.start() for m in re.finditer(r'[a-z][a-z0-9_]*',text.lower()) if m.group() in ts]
 start=max(0,(starts[0] if starts else 0)-180)
 return {'start_char':start,'end_char':min(len(text),start+cap),'text':text[start:start+cap],'truncated':len(text)>cap}
async def native(query,high,low):
 import numpy as np
 from fastembed import TextEmbedding
 from lightrag import LightRAG,QueryParam
 from lightrag.utils import EmbeddingFunc
 embedder=TextEmbedding('BAAI/bge-small-en-v1.5',specific_model_path='/data/xuancheng/retrieval_pilot_20261020/embedding_verified',threads=2,providers=['CPUExecutionProvider'])
 async def embed(texts,**kwargs):
  if any(len(embedder.model.tokenizer.encode(s).ids)>512 for s in texts):raise ValueError('Embedding context too long; no silent truncation')
  return await asyncio.to_thread(lambda:np.array(list(embedder.embed(texts))))
 async def forbidden_llm(*args,**kwargs):raise RuntimeError('Read-only retrieval cannot call a provider or index documents')
 rag=LightRAG(working_dir=str(ROOT/'index'),embedding_func=EmbeddingFunc(embedding_dim=384,func=embed,max_token_size=512,model_name='bge-small-en-v1.5'),llm_model_func=forbidden_llm,llm_model_name='retrieval_only_no_provider',cosine_better_than_threshold=0.1)
 await rag.initialize_storages()
 results={}
 try:
  for mode in ['naive','mix']:
   param=QueryParam(mode=mode,top_k=8,chunk_top_k=5,max_entity_tokens=800,max_relation_tokens=1000,max_total_tokens=5000,enable_rerank=False,hl_keywords=high or [query],ll_keywords=low or [query])
   try:results[mode]=await rag.aquery_data(query,param)
   except Exception as e:results[mode]={'status':'error','error_type':type(e).__name__,'message':str(e)[:150]}
 finally:await rag.finalize_storages()
 return results

def main(payload):
 docs=read_json('documents.json');byid={d['id']:d for d in docs};g=read_json('domain_graph.json');nodes={n['id']:n for n in g['nodes']};edges=g['edges']
 if payload.get('operation')=='read':
  id=payload.get('source_id');start=payload.get('start_char',0);cap=payload.get('max_chars',8000)
  if not isinstance(id,str) or len(id)>200 or type(start)is not int or start<0 or type(cap)is not int or not 100<=cap<=12000:raise ValueError('Invalid bounded source read')
  if id in byid:
   d=byid[id];text=d['text'];assert hashlib.sha256(text.encode()).hexdigest()==d['text_sha256']
   return {'status':'ok','id':id,'source_url':d['url'],'source_scope':d.get('source_scope'),'text':text[start:start+cap],'start_char':start,'next_char':min(len(text),start+cap),'total_chars':len(text),'truncated':start+cap<len(text),'text_sha256':d['text_sha256'],'trust':'untrusted_source_evidence','scientific_status':'not_evaluated','executable':False}
  if id not in nodes:raise ValueError('Unknown registered evidence or graph node ID')
  n=nodes[id];rels=[e for e in edges if e['source']==id or e['target']==id][:35];evidence=[]
  for sp in n.get('evidence',[])[:3]:
   rel=pathlib.PurePosixPath(sp['path'])
   if rel.is_absolute() or '..' in rel.parts:raise ValueError('Invalid source path in frozen graph')
   p=ROOT/'sources'/str(rel)
   if not p.is_file() or p.is_symlink() or not p.resolve().is_relative_to((ROOT/'sources').resolve()):raise ValueError('Source outside registered root')
   raw=p.read_bytes()
   if hashlib.sha256(raw).hexdigest()!=sp['sha256']:raise ValueError('Source digest mismatch')
   lines=raw.decode('utf-8-sig').splitlines();text='\n'.join(lines[sp['line_start']-1:sp['line_end']])
   if hashlib.sha256(text.encode()).hexdigest()!=sp['text_sha256']:raise ValueError('Source span digest mismatch')
   evidence.append({**sp,'text':text[:10000],'truncated':len(text)>10000})
  neighbors={e['target'] if e['source']==id else e['source'] for e in rels}
  return {'status':'ok','node':n,'relations':rels,'neighbor_nodes':[{k:nodes[x].get(k) for k in ['id','type','name','species_scope','registration_to_current_subjects']} for x in sorted(neighbors)[:20]],'original_evidence':evidence,'trust':'untrusted_source_parsed_candidate','scientific_status':'not_evaluated','executable':False}
 query=payload.get('query');limit=payload.get('limit',5);high=payload.get('high_level_keywords',[]);low=payload.get('low_level_keywords',[])
 if not isinstance(query,str) or not 1<=len(query)<=1000 or type(limit)is not int or not 1<=limit<=8:raise ValueError('Invalid bounded research query')
 for ks in [high,low]:
  if not isinstance(ks,list) or len(ks)>8 or any(not isinstance(x,str) or not 1<=len(x)<=150 for x in ks):raise ValueError('Invalid bounded keywords')
 words=set(tokens(query));df=collections.Counter();tf={}
 for d in docs:
  tf[d['id']]=collections.Counter(tokens(d['id']+' '+d.get('heading','')+' '+d['text']));df.update(set(tf[d['id']]))
 lexical=[]
 for d in docs:
  counts=tf[d['id']];score=sum((1+math.log(counts[w]))*math.log(1+len(docs)/(1+df[w])) for w in words if counts[w])
  if score:lexical.append((score,d['id']))
 lexical.sort(key=lambda p:(-p[0],p[1]));ranks={'lexical':[x[1] for x in lexical]}
 native_results=asyncio.run(native(query,high,low));graph_hints=[];native_status={}
 for mode,raw in native_results.items():
  native_status[mode]={'status':raw.get('status'),'error_type':raw.get('error_type'),'message':raw.get('message')}
  got=[];data=raw.get('data',{})
  for row in data.get('chunks',[]):
   for id in str(row.get('file_path','')).split('<SEP>'):
    if id in byid and id not in got:got.append(id)
  ranks['lightrag_'+mode]=got
  if mode=='mix':
   graph_hints={'entities':data.get('entities',[])[:6],'relationships':data.get('relationships',[])[:6]}
 scores=collections.Counter()
 for route,ids in ranks.items():
  for rank,id in enumerate(ids[:15],1):scores[id]+=1/(60+rank)
 stop={'official','source','analysis','brain','volume','data','method','methods','and','or','the','in','of','for','to','a','with','without','statistics','snapshot','versus'}
 anchors=words-stop;eligible=[];anchor_matches={}
 for d in docs:
  title_tokens=set(tokens(d['id']+' '+d.get('heading','')))-stop
  matched=anchors & title_tokens
  if len(matched)>=2:eligible.append(d['id']);anchor_matches[d['id']]=sorted(matched)
 # Explicit entrypoint/title matches define eligibility; missing native index coverage
 # cannot make unrelated graph hits outrank the only source for that entrypoint.
 filtered_scores={id:score for id,score in scores.items() if not eligible or id in eligible}
 selected=sorted(filtered_scores,key=lambda x:(-filtered_scores[x],x))[:limit];sources=[]
 for id in selected:
  d=byid[id];sources.append({'source_id':id,'source_url':d['url'],'heading':d.get('heading'),'source_scope':d.get('source_scope'),'score':scores[id],'parent_chars':len(d['text']),'text_sha256':d['text_sha256'],'excerpt':snippet(d['text'],query),'read_with':'read_research_knowledge(source_id) to inspect the registered parent excerpt'})
 if isinstance(graph_hints,dict):
  for kind in ['entities','relationships']:
   graph_hints[kind]=[row for row in graph_hints.get(kind,[]) if set(str(row.get('file_path','')).split('<SEP>')) & set(selected)]
 domain=[]
 for id,n in nodes.items():
  if n['type'] in ['SourceDocument','EvidenceFragment','LabelVocabularyVersion']:continue
  body=' '.join([n['name'],n.get('species_scope',''),json.dumps(n.get('metadata',{}),ensure_ascii=False)])
  nw=set(tokens(body));score=len(words&nw)
  if str(n.get('label_id','NOT_A_LABEL')) in words:score+=8
  if score:domain.append((score,id,n))
 domain.sort(key=lambda p:(-p[0],p[1]))
 return {'status':'ok','route':'native_LightRAG_naive_mix_plus_lexical_RRF_parent_evidence','sources':sources,'domain_graph_hits':[{'id':id,'type':n['type'],'name':n['name'],'score':score,'label_id':n.get('label_id'),'read_with':'read_research_knowledge(node_id)'} for score,id,n in domain[:min(limit,4)]],'derived_graph_hints':graph_hints,'native_status':native_status,'native_graph_coverage':{'selected_parents_indexed':list(set(selected)&set(ranks.get('lightrag_naive',[])+ranks.get('lightrag_mix',[]))),'selected_parents_lexical_only':[x for x in selected if x not in ranks.get('lightrag_naive',[])+ranks.get('lightrag_mix',[])]},'source_ranks':{k:v[:10] for k,v in ranks.items()},'source_anchor_filter':{'active':bool(eligible),'title_anchor_matches':anchor_matches,'dropped_nonmatching_sources':[x for x in scores if x not in filtered_scores]},'parent_scope_notice':'Parents are registered source excerpts or official snapshots, not necessarily entire papers; graph hints may omit conditions. Read originals before selecting parameters.','trust':'untrusted_candidate_evidence','scientific_status':'not_evaluated','executable':False}
if __name__=='__main__':
 try:
  p=json.loads(sys.stdin.read(20000));out=main(p);print(json.dumps(out,ensure_ascii=False))
 except Exception as e:
  print(json.dumps({'status':'error','error_type':type(e).__name__,'message':str(e)[:250]}));sys.exit(1)
