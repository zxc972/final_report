import pathlib,json,collections
import networkx as nx
r=pathlib.Path(__file__).parent
g=nx.read_graphml(r/'index/graph_chunk_entity_relation.graphml')
chunks=json.loads((r/'index/kv_store_text_chunks.json').read_text())
obj={'nodes':len(g.nodes),'edges':len(g.edges),'node_types':dict(collections.Counter(v.get('entity_type') for _,v in g.nodes(data=True))),'chunks':len(chunks),'entities':[dict(id=k,**v) for k,v in g.nodes(data=True)],'relationships':[dict(source=a,target=b,**v) for a,b,v in g.edges(data=True)]}
(r/'graph_export.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in obj.items() if k not in ['entities','relationships']}))
