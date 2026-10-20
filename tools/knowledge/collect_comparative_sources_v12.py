import importlib.util,json
from pathlib import Path
R=Path('/data/xuancheng/agent_overnight_20261020')
spec=importlib.util.spec_from_file_location('collect',R/'collect_method_sources_v12.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
entries=[('global_gyrification','primary_paper','https://pmc.ncbi.nlm.nih.gov/articles/PMC4156754/'),('comparative_folding','primary_paper','https://elifesciences.org/articles/92080'),('scipy_hull','author_api','https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.ConvexHull.html')]
records=[m.collect(x)for x in entries]
(m.ROOT/'additional_source_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
print(json.dumps([{k:r.get(k)for k in ['id','status','text_chars','attempts']}for r in records],ensure_ascii=False,indent=2))

