"""Read-only local retrieval from a source-parsed software contract graph.

Graph relations and exact source spans are evidence, not executable recipes.
Only the server may configure the root. Model IDs never become paths.
"""
from __future__ import annotations
import collections,copy,hashlib,json,math,os,re,stat
from pathlib import Path

class SourceContractGraph:
    def __init__(self,root:Path):
        original=Path(root)
        if original.is_symlink():raise ValueError('Source graph root must not be a symlink')
        self.root=original.resolve(strict=True)
        self.graph=self._json('graph.json',32*1024*1024)
        if self.graph.get('schema')!='primatex.software_contract_graph.v1':raise ValueError('Unsupported source graph schema')
        nodes=self.graph.get('nodes',[]);edges=self.graph.get('edges',[])
        if not 1<=len(nodes)<=50000 or len(edges)>300000:raise ValueError('Source graph exceeds bounds')
        self.nodes={}
        for n in nodes:
            if not isinstance(n,dict) or not isinstance(n.get('id'),str) or n['id'] in self.nodes:raise ValueError('Invalid or duplicate source graph node')
            if n.get('executable') is not False:raise ValueError('Source graph candidate cannot authorize execution')
            self.nodes[n['id']]=n
        self.neighbors=collections.defaultdict(list)
        for e in edges:
            if e['source'] not in self.nodes or e['target'] not in self.nodes:raise ValueError('Undeclared source graph endpoint')
            self.neighbors[e['source']].append(e);self.neighbors[e['target']].append(e)
        self.docs={}
        self.df=collections.Counter()
        for id,n in self.nodes.items():
            if n['type'] not in ['SoftwareInterface','InputParameter','InputSpec','OutputField','OutputSpec']:continue
            text=' '.join([n.get('name',''),n.get('family',''),n.get('owner',''),n.get('description') or '',json.dumps(n.get('metadata',{}),ensure_ascii=False),n.get('command') if isinstance(n.get('command'),str) else ''])
            words=self._tokens(text);self.docs[id]=collections.Counter(words);self.df.update(set(words))
        self.sha256=hashlib.sha256((self.root/'graph.json').read_bytes()).hexdigest()
    @staticmethod
    def _tokens(text):return re.findall(r'[a-z][a-z0-9_]+',text.lower())
    def _bytes(self,p:Path,limit:int):
        resolved=p.resolve(strict=True)
        if not resolved.is_relative_to(self.root):raise ValueError('Source path outside configured graph root')
        current=self.root
        for part in p.relative_to(self.root).parts:
            current=current/part
            if current.is_symlink():raise ValueError('Source links not allowed')
        if not stat.S_ISREG(p.stat().st_mode) or p.stat().st_size>limit:raise ValueError('Source file outside bounds')
        return p.read_bytes()
    def _json(self,name,limit):return json.loads(self._bytes(self.root/name,limit))
    def search(self,query:str,limit:int=5):
        if not isinstance(query,str) or not 1<=len(query)<=2000:raise ValueError('Bounded nonempty query required')
        if type(limit) is not int or not 1<=limit<=10:raise ValueError('Limit must be 1..10')
        words=set(self._tokens(query));families={n.get('family') for n in self.nodes.values() if n.get('family')};selected=families&words
        if 'freesurfer' in words:selected={'freesurfer'}
        ranked=[];N=max(1,len(self.docs))
        for id,tf in self.docs.items():
            n=self.nodes[id]
            if selected and n.get('family') not in selected:continue
            score=sum((1+math.log(1+tf[w]))*math.log(1+N/(1+self.df[w])) for w in words if w in tf)
            title=n['name'].lower()
            if title in query.lower():score+=12
            if score:ranked.append((score,id,n))
        ranked.sort(key=lambda x:(-x[0],x[1]))
        return {'status':'ok','route':'source_contract_graph_lexical_and_neighbors','graph_sha256':self.sha256,'results':[{'id':id,'name':n['name'],'type':n['type'],'family':n.get('family'),'summary':(n.get('description') or n.get('metadata',{}).get('desc') or '')[:800],'source':copy.deepcopy(n.get('source')),'score':round(score,4),'review_status':'source_parsed_candidate','executable':False} for score,id,n in ranked[:limit]],'trust':'untrusted_source_evidence','scientific_status':'not_evaluated','runtime_version_binding':'not_verified'}
    def read(self,id:str):
        if not isinstance(id,str) or id not in self.nodes:raise KeyError('Unknown graph node ID')
        n=copy.deepcopy(self.nodes[id]);s=n.get('source')
        if not s or 'path' not in s:raise ValueError('Node has no source span')
        parts=Path(s['path']).parts
        if Path(s['path']).is_absolute() or '..' in parts:raise ValueError('Invalid registered source path')
        raw=self._bytes(self.root/'sources'/s['path'],2*1024*1024)
        if hashlib.sha256(raw).hexdigest()!=s['sha256']:raise ValueError('Source checksum mismatch')
        lines=raw.decode('utf-8-sig').splitlines();start=max(1,int(s.get('line_start',1)));end=min(len(lines),int(s.get('line_end',len(lines))),start+159)
        excerpt='\n'.join(lines[start-1:end]);truncated=len(excerpt)>14000 or end<int(s.get('line_end',len(lines)))
        excerpt=excerpt[:14000]
        relations=copy.deepcopy(self.neighbors[id][:30]);neighbor_ids=[]
        for e in relations:
            other=e['target'] if e['source']==id else e['source']
            if other not in neighbor_ids:neighbor_ids.append(other)
        neighbors=[{k:copy.deepcopy(self.nodes[x].get(k)) for k in ['id','type','name','family','metadata','source']} for x in neighbor_ids[:20]]
        return {'id':id,'node':n,'relations':relations,'neighbor_nodes':neighbors,'evidence':{'url':s['url'],'sha256':s['sha256'],'line_start':start,'line_end':end,'text':excerpt,'truncated':truncated},'review_status':'source_parsed_candidate','trust':'untrusted_source_evidence','scientific_status':'not_evaluated','runtime_version_binding':'Nipype wrapper commit only; installed CLI compatibility unverified','executable':False,'notice':'Source-defined interface/parameter contracts. Imported/inherited fields and scientific applicability may be incomplete. Never treat this record as automatic execution permission.'}
