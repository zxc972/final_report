"""Native LightRAG retrieval pilot. Credentials stay server-side; no image data used."""
import asyncio, contextvars, hashlib, json, os, pathlib, time, traceback
from collections import Counter
ROOT=pathlib.Path(__file__).resolve().parent
os.environ['TIKTOKEN_CACHE_DIR']=str(ROOT.parent/'tokenizer_cache')
import numpy as np
import tiktoken
from fastembed import TextEmbedding
from openai import AsyncOpenAI
from lightrag import LightRAG,QueryParam
from lightrag.utils import EmbeddingFunc
phase=contextvars.ContextVar('phase',default='index')
for d in ['http','retrieval','answers','contexts']:(ROOT/d).mkdir(exist_ok=True)
def save(p,obj):
 p=ROOT/p;p.parent.mkdir(exist_ok=True,parents=True)
 tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2));tmp.replace(p)
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
cfg={}
for line in pathlib.Path('/data/xuancheng/eval/ft01_20261018/config/.env').read_text().splitlines():
 if '=' in line and not line.lstrip().startswith('#'):
  k,v=line.split('=',1);cfg[k.strip()]=v.strip().strip('\"\'')
base=cfg['FT01_BASE_URL'].rstrip('/')
if base=='https://inferaiapi.com':base+='/v1'
assert base=='https://inferaiapi.com/v1'
client=AsyncOpenAI(api_key=cfg['PLATFORM_API_KEY'],base_url=base,timeout=150,max_retries=0)
MODEL='deepseek-v4-pro';CAP=80
ledger=read('provider_budget.json') if (ROOT/'provider_budget.json').exists() else {'http_started':0,'limit':CAP,'known_prompt_tokens':0,'known_completion_tokens':0,'usage_unknown_requests':0}
llm_slots=asyncio.Semaphore(3)
pacing_lock=asyncio.Lock()
last_start=0.0
async def llm(prompt,system_prompt=None,history_messages=None,**kwargs):
 global last_start
 msgs=([{'role':'system','content':system_prompt}] if system_prompt else [])+(history_messages or [])+[{'role':'user','content':prompt}]
 fmt=kwargs.get('response_format')
 if kwargs.get('keyword_extraction') or kwargs.get('response_format_json_object'):fmt={'type':'json_object'}
 for attempt in range(2):
  async with llm_slots:
   async with pacing_lock:
    await asyncio.sleep(max(0,7.0-(time.monotonic()-last_start)))
    last_start=time.monotonic()
   if ledger['http_started']>=CAP:raise RuntimeError('HTTP budget exhausted')
   ledger['http_started']+=1;i=ledger['http_started'];save('provider_budget.json',ledger)
   req={'model':MODEL,'messages':msgs,'temperature':0,'max_tokens':8000,'extra_body':{'thinking':{'type':'disabled'}}}
   if fmt:req['response_format']=fmt
   audit={'id':i,'phase':phase.get(),'started':time.time(),'attempt':attempt,'request':req}
   save(f'http/{i:03d}.json',audit)
   try:
    res=await client.chat.completions.create(**req)
    audit['response']=res.model_dump();audit['seconds']=round(time.time()-audit['started'],3)
    usage=res.usage
    if usage:
     ledger['known_prompt_tokens']+=usage.prompt_tokens;ledger['known_completion_tokens']+=usage.completion_tokens
    else:ledger['usage_unknown_requests']+=1
    save('provider_budget.json',ledger);save(f'http/{i:03d}.json',audit)
    txt=res.choices[0].message.content or ''
    if res.choices[0].finish_reason=='length':raise ValueError('truncated response')
    if fmt:
     trimmed=txt.strip()
     if trimmed.startswith('```') and trimmed.endswith('```') and trimmed.count('```')==2:
      trimmed=trimmed.split('\n',1)[1].rsplit('```',1)[0].strip()
      audit['normalization']='single complete outer code fence removed';save(f'http/{i:03d}.json',audit)
     json.loads(trimmed);txt=trimmed
    print(json.dumps({'http':i,'phase':phase.get(),'status':'ok','seconds':audit['seconds']}),flush=True)
    return txt
   except Exception as e:
    # No raw exception text: SDK errors may echo provider details.
    audit['error_type']=type(e).__name__;audit['seconds']=round(time.time()-audit['started'],3)
    if 'response' not in audit:ledger['usage_unknown_requests']+=1
    save('provider_budget.json',ledger);save(f'http/{i:03d}.json',audit)
    print(json.dumps({'http':i,'phase':phase.get(),'error':type(e).__name__}),flush=True)
    if attempt or type(e).__name__ not in ['APITimeoutError','APIConnectionError','InternalServerError','RateLimitError']:raise
    if type(e).__name__=='RateLimitError':await asyncio.sleep(55)

encoder=tiktoken.encoding_for_model('gpt-4o-mini')
embedder=TextEmbedding('BAAI/bge-small-en-v1.5',specific_model_path=str(ROOT.parent/'embedding_verified'),threads=2,providers=['CPUExecutionProvider'])
embed_audit=read('embedding_audit.json') if (ROOT/'embedding_audit.json').exists() else []
async def embed(texts,**kwargs):
 lengths=[len(embedder.model.tokenizer.encode(s).ids) for s in texts]
 embed_audit.append({'phase':phase.get(),'n':len(texts),'token_lengths':lengths})
 save('embedding_audit.json',embed_audit)
 return await asyncio.to_thread(lambda:np.array(list(embedder.embed(texts))))
SETTINGS={'top_k':8,'chunk_top_k':4,'max_entity_tokens':500,'max_relation_tokens':700,'max_total_tokens':3500,'enable_rerank':False}
SYSTEM='Answer the exact research question only from the supplied context. Identify the exact method, executable entrypoint, input type, requested operation and scope before deciding. An alternative that requires changing the input does not make the originally requested operation valid. Graph descriptions are retrieval hints; source chunks govern claims. Preserve uncertainty and modal strength (may, sometimes, usually, not easily) and software-version scope. A command example demonstrates usage, not whether every parameter or dependency is mandatory. A rule about one processing stage does not establish inclusion rules for later stages. Evidence silence is unknown, not evidence of permission or prohibition. If a source explicitly states an input contract, do not simultaneously list that contract as unknown. Return concise JSON: {"answer_summary":"direct answer with qualifications", "established":[{"statement":"...","evidence":[{"source_id":"...","quote":"short verbatim quote"}]}], "conditions":[{"statement":"...","evidence":[{"source_id":"...","quote":"..."}]}], "exceptions":[{"statement":"...","evidence":[{"source_id":"...","quote":"..."}]}], "not_established":["..."],"source_scope":"..."}. Maximum 8 total entries across established/conditions/exceptions. Audit your answer_summary against the entries: it must not claim anything stronger, remove a condition, or contradict not_established. Never cite a source absent from chunks. No code fences.'
SOURCE_REGISTRY={x['id']:x for x in read('expanded_corpus.json')}
def pack(raw,mode):
 data=raw.get('data',{});out={'chunks':[],'entities':[],'relationships':[]}
 # Equal total ceiling, explicitly accounting for JSON metadata. No reference answers.
 caps={'chunks':1800 if mode=='naive' else 1450,'entities':1600,'relationships':1800}
 for kind in ['chunks','entities','relationships']:
  for row in data.get(kind,[]):
   if kind=='chunks':
    source=SOURCE_REGISTRY[row['file_path']]
    scope=source.get('source_scope','Snapshot documentation; installed software version unverified.')
    if row['file_path'] in ['LONG','PED']:scope='FreeSurfer historical documentation FS 5.1, 5.2, 5.3, 6.0; installed version unverified.'
    item={'source_id':row['file_path'],'chunk_id':row['chunk_id'],'text':row['content'],'source_scope':scope}
   elif kind=='entities':item={k:row.get(k) for k in ['entity_name','entity_type','description','file_path']}
   else:item={k:row.get(k) for k in ['src_id','tgt_id','description','keywords','file_path']}
   out[kind].append(item)
   if len(encoder.encode(json.dumps(out,ensure_ascii=False)))>caps[kind]:out[kind].pop()
 return out,{'total_serialized_context':len(encoder.encode(json.dumps(out,ensure_ascii=False)))}
async def main():
 save('run_status.json',{'state':'initializing','time':time.time()})
 settings={'model':MODEL,'base_url':base,'embedding_model':'BAAI/bge-small-en-v1.5 (Qdrant ONNX quantized)','embedding_dim':384,'query_settings':SETTINGS,'chunk_tokens':280,'chunk_overlap':50,'extract_json':True,'gleaning':0,'language':'English','context_caps':{'total':1800,'mix_chunks_stage':1450,'mix_entities_stage':1600},'comparison':'expanded native naive vs mix; shared 1800-token context ceiling; actual lengths differ; source metadata attached to every chunk','answer_system_prompt':SYSTEM,'max_http':CAP,'repeat':2,'min_request_interval_seconds':7,'review_targets_sent_to_model':False}
 save('run_config.json',settings)
 rag=LightRAG(working_dir=str(ROOT/'index'),embedding_func=EmbeddingFunc(embedding_dim=384,func=embed,max_token_size=512,model_name='bge-small-en-v1.5'),llm_model_func=llm,llm_model_name=MODEL,chunk_token_size=280,chunk_overlap_token_size=50,embedding_chunk_overlap_token_size=50,entity_extraction_use_json=True,entity_extract_max_gleaning=0,entity_extract_max_records=60,entity_extract_max_entities=25,llm_model_max_async=3,max_parallel_insert=2,default_llm_timeout=330,cosine_better_than_threshold=0.1)
 await rag.initialize_storages()
 try:
  corpus=read('expanded_corpus.json')
  docs=[f"SOURCE_ID: {x['id']}\nSOURCE_URL: {x['url']}\nSCOPE: {x.get('source_scope','Excerpt from the cited document; installed software version is not verified.')}\nHEADING: {x.get('heading','')}\n\n{x['text']}" for x in corpus]
  save('indexed_documents.json',[{'id':x['id'],'text':t,'sha256':hashlib.sha256(t.encode()).hexdigest()} for x,t in zip(corpus,docs)])
  if not (ROOT/'index_complete.json').exists():
   phase.set('index');save('run_status.json',{'state':'indexing','time':time.time()})
   await rag.ainsert(docs,ids=[x['id'] for x in corpus],file_paths=[x['id'] for x in corpus])
   statuses=await rag.doc_status.get_status_counts();save('index_status.json',statuses)
   if statuses.get('processed',0)!=len(corpus):raise RuntimeError('Index incomplete; query run prohibited')
   save('index_complete.json',{'count':len(corpus),'time':time.time()})
  save('run_status.json',{'state':'querying','time':time.time()})
  jobs=asyncio.Semaphore(2)
  async def run_case(q,mode):
   ident=q['id']+'_'+mode
   async with jobs:
    phase.set('retrieve_'+ident)
    p=ROOT/f'retrieval/{ident}.json'
    if p.exists():raw=read(f'retrieval/{ident}.json')
    else:
     raw=await rag.aquery_data(q['question'],QueryParam(mode=mode,**SETTINGS));save(f'retrieval/{ident}.json',raw)
    if raw.get('status')!='success':raise RuntimeError('Retrieval failed '+ident)
    ctx,counts=pack(raw,mode);save(f'contexts/{ident}.json',{'question':q['question'],'context':ctx,'token_counts':counts})
    for rep in [1,2]:
     outid=ident+f'_r{rep}'
     if (ROOT/f'answers/{outid}.json').exists():continue
     phase.set('answer_'+outid)
     txt=await llm(json.dumps({'question':q['question'],'context':ctx},ensure_ascii=False),system_prompt=SYSTEM,response_format={'type':'json_object'})
     answer=json.loads(txt)
     for k in ['established','conditions','exceptions','not_established']:assert isinstance(answer[k],list)
     assert isinstance(answer['answer_summary'],str)
     save(f'answers/{outid}.json',answer);print('ANSWER_SAVED '+outid,flush=True)
  tasks=[run_case(q,m) for q in read('frozen_questions.json') for m in ['naive','mix']]
  done=await asyncio.gather(*tasks,return_exceptions=True)
  errors=[{'type':type(x).__name__,'message':str(x)[:180]} for x in done if isinstance(x,Exception)]
  save('run_status.json',{'state':'complete' if not errors else 'partial','errors':errors,'answers_saved':len(list((ROOT/'answers').glob('*.json'))),'time':time.time()})
 finally:
  await rag.finalize_storages();await client.close()
if __name__=='__main__':
 try:asyncio.run(main())
 except Exception as e:
  save('run_status.json',{'state':'failed','error_type':type(e).__name__,'time':time.time()});traceback.print_exc();raise

