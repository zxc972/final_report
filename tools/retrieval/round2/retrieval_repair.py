import asyncio,json,collections,time
from run_expanded import ROOT,read,save,llm,client,phase,encoder,SYSTEM,embed,MODEL,SOURCE_REGISTRY
from lightrag import LightRAG,QueryParam
from lightrag.utils import EmbeddingFunc
DECOMP='''Split the user's compound research question into 2 to 4 concise search questions, each targeting a distinct requested fact or applicability condition. Preserve software names, specific entrypoints and scope. Do not answer the question, invent facts, add source IDs, or use external knowledge. Return JSON {"queries":["..."]}.'''
async def main():
 save('retrieval_repair_protocol.json',{'cases':['X04','X05'],'created':time.time(),'decomposition_prompt':DECOMP,'method':'LLM subquestions -> native naive per subquestion -> union by parent source -> source-diverse complete parent excerpts','context_cap':1800,'repeats':2,'prior_index_unchanged':True,'reference_methods':['LangChain MultiQueryRetriever','LangChain ParentDocumentRetriever'],'custom_adapter_not_native_LightRAG_mode':True,'post_hoc_development':True,'gold_sources_used':False})
 rag=LightRAG(working_dir=str(ROOT/'index'),embedding_func=EmbeddingFunc(embedding_dim=384,func=embed,max_token_size=512,model_name='bge-small-en-v1.5'),llm_model_func=llm,llm_model_name=MODEL,chunk_token_size=280,chunk_overlap_token_size=50,embedding_chunk_overlap_token_size=50,entity_extraction_use_json=True,entity_extract_max_gleaning=0,cosine_better_than_threshold=0.1)
 await rag.initialize_storages()
 try:
  for q in read('frozen_questions.json'):
   if q['id'] not in ['X04','X05']:continue
   ident=q['id'];phase.set('decompose_'+ident)
   queries=json.loads(await llm(q['question'],system_prompt=DECOMP,response_format={'type':'json_object'}))['queries'];assert 2<=len(queries)<=4
   traces=[];rank_scores=collections.defaultdict(float);firsts=[]
   for sq in queries:
    raw=await rag.aquery_data(sq,QueryParam(mode='naive',top_k=8,chunk_top_k=4,max_total_tokens=3500,enable_rerank=False))
    assert raw['status']=='success';traces.append({'subquery':sq,'result':raw});seen=set()
    for rank,row in enumerate(raw['data']['chunks'],1):
     sid=row['file_path']
     if rank==1 and sid not in firsts:firsts.append(sid)
     if sid not in seen:rank_scores[sid]+=1/(60+rank);seen.add(sid)
   ordered=firsts+[x for x in sorted(rank_scores,key=lambda x:-rank_scores[x]) if x not in firsts]
   ctx={'chunks':[],'entities':[],'relationships':[]};skipped=[]
   for sid in ordered:
    source=SOURCE_REGISTRY[sid];scope=source.get('source_scope','Snapshot; installed software version not verified.')
    if sid in ['PED','LONG']:scope='Historical FreeSurfer FS 5.1, 5.2, 5.3, 6.0; installed version unverified.'
    item={'source_id':sid,'chunk_id':sid+'-parent','text':source['text'],'source_scope':scope}
    ctx['chunks'].append(item)
    if len(encoder.encode(json.dumps(ctx,ensure_ascii=False)))>1800:ctx['chunks'].pop();skipped.append(sid)
   save(f'multiquery_traces/{ident}.json',{'queries':queries,'traces':traces,'ordering':ordered,'skipped_for_budget':skipped})
   save(f'multiquery_contexts/{ident}.json',{'question':q['question'],'context':ctx,'tokens':len(encoder.encode(json.dumps(ctx,ensure_ascii=False)))})
   for rep in [1,2]:
    phase.set(f'multiquery_answer_{ident}_r{rep}')
    result=json.loads(await llm(json.dumps({'question':q['question'],'context':ctx},ensure_ascii=False),system_prompt=SYSTEM,response_format={'type':'json_object'}))
    save(f'multiquery_answers/{ident}_r{rep}.json',result);print('SAVED '+ident+f'_r{rep}',flush=True)
 finally:await rag.finalize_storages();await client.close()
if __name__=='__main__':asyncio.run(main())
