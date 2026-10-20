"""Freeze method graph and original source release, retaining raw/rejected extractions."""
from pathlib import Path
import collections,hashlib,json,re,shutil,time
R=Path('/data/xuancheng/agent_overnight_20261020');P=R/'method_graph_loop_20261020';D=R/'research_evidence_v12'
assert not D.exists();shutil.copytree(R/'research_evidence_v11',D)
manifests=['source_manifest.json','pdf_source_manifest.json','additional_source_manifest.json','curvature_source_manifest.json']
all_sources=sum([json.loads((P/n).read_text())for n in manifests],[])
sources={s['id']:s for s in all_sources if s['status']=='downloaded'}
docs=json.loads((D/'documents.json').read_text());domain=json.loads((D/'domain_graph.json').read_text())
nodes=[];edges=[];methods=[];transforms=[];quarantine=[];seen={}
types={'inputs':('InputRequirement','REQUIRES_INPUT'),'conditions':('ApplicabilityCondition','HAS_CONDITION'),'steps':('AnalysisStep','HAS_STEP'),'checks':('VerificationCheck','VERIFIED_BY'),'exceptions':('MethodException','HAS_EXCEPTION'),'outputs':('OutputArtifact','PRODUCES'),'parameters':('MethodParameter','HAS_PARAMETER')}
for sid,s in sources.items():
 text=(P/'sources'/(sid+'.txt')).read_text();assert hashlib.sha256(text.encode()).hexdigest()==s['text_sha256']
 filename='method_'+sid+'.txt';(D/'sources'/filename).write_text(text)
 docs.append({'id':'METHOD_SOURCE_'+sid,'url':s['url'],'heading':sid.replace('_',' ')+' method source original','text':text,'text_sha256':s['text_sha256'],'source_scope':s['evidence_class']+'; full downloaded page/PDF text snapshot, may include navigation; blog examples are not universal recommendations; not expert reviewed or native LightRAG reindexed.'})
 nodes.append({'id':'method-source:'+sid,'type':'SourceDocument','name':sid.replace('_',' '),'url':s['url'],'source_paths':[filename],'review_status':'source_snapshot_candidate','scientific_status':'not_expert_reviewed','executable':False})
def span(sid,quote):
 text=(P/'sources'/(sid+'.txt')).read_text()
 pos=text.find(quote);actual=quote;transform='none'
 if pos<0:
  parts=quote.split()
  if not parts:return None
  match=re.search(r'\s+'.join(map(re.escape,parts)),text)
  if not match:return None
  pos=match.start();actual=text[match.start():match.end()];transform='whitespace_only_original_span_reconstruction'
 if not 8<=len(actual)<=600:return None
 lo=text.count('\n',0,pos)+1;hi=text.count('\n',0,pos+len(actual))+1
 lines=text.splitlines();e={'path':'method_'+sid+'.txt','sha256':sources[sid]['text_sha256'],'line_start':lo,'line_end':hi,'text_sha256':hashlib.sha256('\n'.join(lines[lo-1:hi]).encode()).hexdigest()}
 return actual,e,transform
def node_for(mid,cat,c):
 typ,rel=types[cat];canonical=(typ,mid,re.sub(r'\s+',' ',c['statement']).strip().lower())
 if canonical in seen:return seen[canonical]
 nid='method-fact:'+hashlib.sha256(json.dumps(canonical).encode()).hexdigest()[:24];seen[canonical]=nid
 n={'id':nid,'type':typ,'name':c['statement'],'evidence':[c['evidence']],'metadata':{'method_id':mid,'claim_type':c['claim_type'],'source_id':c['source_id'],'source_quote':c['quote'],'evidence_class':sources[c['source_id']]['evidence_class']},'review_status':'AI_assisted_candidate','scientific_status':'not_expert_reviewed','executable':False}
 nodes.append(n);edges.append({'source':nid,'target':'method-source:'+c['source_id'],'type':'SUPPORTED_BY','evidence':[c['evidence']]})
 return nid
for f in sorted((P/'extractions').glob('*.json')):
 if '.input.'in f.name or '.failure.'in f.name:continue
 extracted=json.loads(f.read_text());batch=extracted['method_id'];httpid=extracted['source_extraction_http_id']
 audit=json.loads((R/'audit'/('http_%04d.json'%httpid)).read_text());content=audit['response']['choices'][0]['message']['content'].strip()
 match=re.fullmatch(r'\x60\x60\x60(?:json)?\s*\n([\s\S]*?)\n\x60\x60\x60',content)
 original=json.loads(match.group(1)if match else content)
 mid='method:v12:'+batch
 card={k:original.get(k)for k in ['name','purpose','species_scope','software']}
 card.update(id=mid,source_ids=extracted['source_ids'],source_extraction_http_id=httpid,scientific_status='not_expert_reviewed',executable=False)
 nodes.append({'id':mid,'type':'AnalysisMethod','name':card['name'],'species_scope':card['species_scope'],'metadata':{'purpose':card['purpose'],'software':card['software']},'review_status':'AI_assisted_candidate','scientific_status':'not_expert_reviewed','executable':False})
 bad=0
 for cat in types:
  card[cat]=[]
  for order,c in enumerate(original[cat]):
   if not isinstance(c,dict)or c.get('source_id')not in sources or c.get('source_id')not in card['source_ids']or c.get('claim_type')not in ['direct','application_inference']or not isinstance(c.get('quote'),str)or not isinstance(c.get('statement'),str):
    quarantine.append({'method_id':mid,'category':cat,'claim':c,'reason':'invalid_claim_schema'});bad+=1;continue
   bind=span(c['source_id'],c['quote'])
   if not bind:
    quarantine.append({'method_id':mid,'category':cat,'claim':c,'reason':'exact_or_whitespace_equivalent_original_quote_missing'});bad+=1;continue
   actual,e,transform=bind
   if transform!='none':transforms.append({'method_id':mid,'category':cat,'model_quote':c['quote'],'actual_original_quote':actual,'source_id':c['source_id'],'transform':transform})
   claim={**c,'quote':actual,'evidence':e,'source_order':order}
   context=bool(re.search(r'\b(was used|were used|was tested|were tested|was installed|in their tests|in this study|used for testing)\b',c['statement'],re.I))
   if context:claim['scope']='source_case_context_not_universal_requirement'
   nid=node_for(mid,cat,claim);claim['id']=nid;card[cat].append(claim)
   edge={'source':mid,'target':nid,'type':types[cat][1],'order':order}
   if context:edge['condition_role']='source_case_context_not_universal'
   edges.append(edge)
  if cat=='steps':
   for a,b in zip(card[cat],card[cat][1:]):edges.append({'source':a['id'],'target':b['id'],'type':'NEXT_DOCUMENTED_STEP','scope':'Accepted source-extracted sequence; may omit quarantined steps, inspect original recipe.'})
 for sid in card['source_ids']:edges.append({'source':mid,'target':'method-source:'+sid,'type':'DOCUMENTED_IN'})
 card['coverage_status']='partial_source_extraction_read_original'if bad else'source_extraction_quote_bound_not_expert_reviewed'
 card['quarantined_claim_count']=bad
 if batch=='hcp_structural_pipeline':card['scope_note']='Personal tutorial tested versions/system; not a general minimum-version or required-OS contract. Official pipeline compatibility must be checked.'
 if batch=='existing_curvature_sulc_profile':card['scope_note']='Different pipelines can define curvature/sulcal depth differently. Do not reinterpret a provided FreeSurfer sulc field as the alpha-surface distance of another study without provenance.'
 methods.append(card)
graph={'schema':'primatex.method_graph.v1','created':time.time(),'methods':methods,'nodes':nodes,'edges':edges,'sources':list(sources.values()),'review_scope':'Real model extraction; literal/whitespace span validation plus AI-assisted scope review; not expert scientific approval. No study expected answers supplied.'}
(D/'method_graph.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2))
old_ids={n['id']for n in domain['nodes']};assert not old_ids&{n['id']for n in nodes}
domain['nodes']+=nodes;domain['edges']+=edges
ids={n['id']for n in domain['nodes']};assert len(ids)==len(domain['nodes'])and all(e['source']in ids and e['target']in ids for e in domain['edges'])
(D/'domain_graph.json').write_text(json.dumps(domain,ensure_ascii=False,indent=2));(D/'documents.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2))
cfg=json.loads((D/'config.json').read_text());cfg.update(created=time.time(),predecessor='research_evidence_v11',sources=len(docs),method_graph_sha256=hashlib.sha256((D/'method_graph.json').read_bytes()).hexdigest(),documents_sha256=hashlib.sha256((D/'documents.json').read_bytes()).hexdigest(),domain_graph_sha256=hashlib.sha256((D/'domain_graph.json').read_bytes()).hexdigest(),native_graph='Frozen native LightRAG index unchanged. New source parents plus explicit method/condition/step neighborhoods, actual provider extraction. New original evidence remains lexical/method graph, not falsely claimed native reindex.')
cfg['snapshot_files']={str(p.relative_to(D)):hashlib.sha256(p.read_bytes()).hexdigest()for p in D.rglob('*')if p.is_file()and p.name!='config.json'}
(D/'config.json').write_text(json.dumps(cfg,indent=2))
(P/'method_quote_transform_audit.json').write_text(json.dumps(transforms,ensure_ascii=False,indent=2));(P/'method_claim_quarantine.json').write_text(json.dumps(quarantine,ensure_ascii=False,indent=2))
audit={'time':time.time(),'release':D.name,'method_cards':len(methods),'new_method_graph_nodes':len(nodes),'new_method_graph_edges':len(edges),'new_node_types':dict(collections.Counter(n['type']for n in nodes)),'existing_label_definitions':sum(n['type']=='LabelDefinition'for n in domain['nodes']),'total_mixed_nodes':len(domain['nodes']),'total_edges':len(domain['edges']),'registered_parent_snapshots':len(docs),'unique_source_urls':len({d['url']for d in docs}),'quarantined_claims':len(quarantine),'whitespace_original_span_reconstructions':len(transforms),'native_index_changed':False,'expert_review':False,'deduplication_scope':'Exact normalized statement within method context; not an expert ontology equivalence count. Software labels and source snapshots are separate types.','provider_extraction_http_ids':[m['source_extraction_http_id']for m in methods],'failed_extraction_preserved':'crossspecies_alignment two failed HTTP attempts; no third retry'}
(P/'release_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(json.dumps(audit,ensure_ascii=False,indent=2))

