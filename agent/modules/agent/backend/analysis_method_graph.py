"""Read-only source-bound method neighborhoods, including prerequisites and ordered steps.
Candidate extraction is not expert review. Declared condition coverage never authorizes execution.
"""
from __future__ import annotations
import hashlib,json,re,stat
from pathlib import Path
from typing import Any

_TYPES={'inputs':'InputRequirement','conditions':'ApplicabilityCondition','steps':'AnalysisStep',
        'checks':'VerificationCheck','exceptions':'MethodException','outputs':'OutputArtifact','parameters':'MethodParameter'}
def tokens(text):
    text=str(text).lower()
    lex={'面积':'surface area mesh','曲率':'curvature','脑沟':'sulcal depth','折叠':'gyrification','猴':'macaque nonhuman primate','跨物种':'crossspecies alignment correspondence','分割':'segmentation','配准':'registration','质量':'qc quality','前置':'prerequisite','体素':'voxel vbm','条件':'conditions','步骤':'steps','纠错':'failure checks'}
    for k,v in lex.items():
        if k in text:text+=' '+v
    return set(re.findall(r'[a-z0-9_.-]+|[\u3400-\u9fff]{2}',text))
class MethodGraph:
    def __init__(self,root:Path,unified_store=None):
        self.unified_store=unified_store
        original=Path(root)
        if original.is_symlink():raise ValueError('Method graph root must not be a symlink')
        self.root=original.resolve(strict=True)
        raw=self._read('config.json',2*1024*1024);self.config=json.loads(raw)
        self.digest=self.config.get('method_graph_sha256')
        if not isinstance(self.digest,str)or not re.fullmatch('[a-f0-9]{64}',self.digest):
            raise ValueError('No registered method graph release')
        self._load()
    def _read(self,name,limit):
        if not isinstance(name,str)or '/'in name or '\\'in name or '..'in name:raise ValueError('Registered release filename required')
        p=self.root/name
        if p.is_symlink()or not p.resolve().is_relative_to(self.root)or not stat.S_ISREG(p.lstat().st_mode):raise ValueError('Invalid method release file')
        raw=p.read_bytes()
        if len(raw)>limit:raise ValueError('Method release exceeds bounds')
        return raw
    def _load(self):
        if self.unified_store is None:
            raw=self._read('method_graph.json',8*1024*1024)
            if hashlib.sha256(raw).hexdigest()!=self.digest:raise ValueError('Method graph digest mismatch')
            obj=json.loads(raw)
        else:
            obj, registered_digest=self.unified_store.document('method_graph')
            if registered_digest != self.digest:
                raise ValueError('Unified method graph release mismatch')
        if obj.get('schema')!='primatex.method_graph.v1':raise ValueError('Unknown method graph schema')
        cards=obj.get('methods',[])
        if not isinstance(cards,list)or len(cards)>256:raise ValueError('Invalid method catalogue')
        self.methods={m['id']:m for m in cards}
        if len(self.methods)!=len(cards):raise ValueError('Duplicate method IDs')
        self.nodes={n['id']:n for n in obj['nodes']};self.edges=obj['edges']
        if len(self.nodes)!=len(obj['nodes'])or any(e['source']not in self.nodes or e['target']not in self.nodes for e in self.edges):raise ValueError('Invalid graph endpoints')
        self.sources={s['id']:s for s in obj['sources']}
        from .analysis_method_overlay import overlay
        extra, self.overlay_digest = overlay()
        self.methods.update({m['id']:m for m in extra['methods'] if m['id'] not in self.methods})
        self.nodes.update({n['id']:n for n in extra['nodes'] if n['id'] not in self.nodes})
        self.sources.update({s['id']:s for s in extra['sources'] if s['id'] not in self.sources})
        self.edges += extra['edges']
    def search(self,query:str,limit:int=5):
        if not isinstance(query,str)or not 1<=len(query)<=1000 or type(limit)is not int or not 1<=limit<=8:raise ValueError('Bounded query and integer limit 1..8 required')
        self._load();words=tokens(query);ranked=[]
        for m in self.methods.values():
            title=tokens(m['name']+' '+m['id']+' '+m.get('purpose','')+' '+' '.join(m.get('software',[])))
            body=tokens(json.dumps(m,ensure_ascii=False))
            score=6*len(words&title)+len(words&body)
            if score:ranked.append((score,m))
        ranked.sort(key=lambda pair:(-pair[0],pair[1]['id']))
        return {'status':'ok','route':'typed_method_graph_lexical_entrypoint_then_explicit_neighborhood','release_sha256':self.digest,
                'results':[{'method_id':m['id'],'name':m['name'],'purpose':m.get('purpose'),'species_scope':m.get('species_scope'),
                   'software':m.get('software',[]),'score':score,'condition_count':len(m.get('conditions',[])),'ordered_step_count':len(m.get('steps',[])),
                   'source_ids':m['source_ids'],'read_with':'read_analysis_method(method_id)','review_status':'AI_assisted_candidate_not_expert_reviewed'}for score,m in ranked[:limit]],
                'notices':['Method candidates are source-grounded planning evidence, not installed capabilities or permission to execute.','Species, units, atlas, coordinate space and observed inputs must be checked.']}
    def read(self,method_id:str):
        self._load()
        if not isinstance(method_id,str)or method_id not in self.methods:raise ValueError('Unknown registered method ID')
        m=self.methods[method_id]
        relation_ids=set([method_id])
        outgoing=[e for e in self.edges if e['source']==method_id]
        for e in outgoing:relation_ids.add(e['target'])
        rels=[e for e in self.edges if e['source']in relation_ids]
        evidence=[]
        for sid in m['source_ids']:
            s=self.sources[sid]
            evidence.append({'source_id':sid,'url':s['url'],'evidence_class':s['evidence_class'],'text_sha256':s['text_sha256'],
                             'read_full_with':'read_research_knowledge("METHOD_SOURCE_'+sid+'")'})
        return {'status':'ok','method':m,'relations':rels[:150],'neighbor_nodes':[self.nodes[i]for i in sorted(relation_ids)if i in self.nodes][:90],
                'source_evidence':evidence,'release_sha256':self.digest,'review_status':'AI_assisted_candidate_exact_quote_checked_semantics_not_expert_reviewed',
                'overlay_sha256':self.overlay_digest,'executable':False,'scientific_status':'not_evaluated'}
    def assess(self,method_id:str,observed_conditions:list[dict[str,Any]]):
        m=self.read(method_id)['method']
        if not isinstance(observed_conditions,list)or len(observed_conditions)>32:raise ValueError('Bounded observed condition list required')
        valid={c['id']:c for c in m.get('inputs',[])+m.get('conditions',[])}
        seen=set();rows=[]
        for item in observed_conditions:
            if not isinstance(item,dict)or item.get('condition_id')not in valid or item['condition_id']in seen:raise ValueError('Conditions must be unique registered input/condition IDs')
            cid=item['condition_id'];seen.add(cid);status=item.get('status')
            if status not in ['supported','contradicted','unknown']:raise ValueError('Use supported, contradicted or unknown')
            ref=item.get('observation_ref','');reason=item.get('reason','')
            if not isinstance(ref,str)or len(ref)>400 or not isinstance(reason,str)or len(reason)>1000:raise ValueError('Bounded observation references required')
            if status!='unknown'and not ref:raise ValueError('A claim of observed support/contradiction needs an observation reference')
            rows.append({'condition_id':cid,'status':status,'observation_ref':ref,'reason':reason})
        missing=[{'condition_id':cid,'status':'unknown','statement':valid[cid]['statement']}for cid in valid if cid not in seen]
        contradicted=[x for x in rows if x['status']=='contradicted']
        unknown=missing+[x for x in rows if x['status']=='unknown']
        return {'status':'ok','method_id':method_id,'condition_coverage_status':'contradicted'if contradicted else('unknown'if unknown else'all_declared_supported'),
                'observations':rows,'unresolved':unknown,'contradictions':contradicted,
                'observation_trust':'Model-declared references; tool does not independently verify their contents or physical provenance.',
                'eligible_for_automatic_execution':False,'scientific_status':'not_evaluated','release_sha256':self.digest}

