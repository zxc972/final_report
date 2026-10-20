"""Collect public method evidence only; no study inputs or credentials."""
from pathlib import Path
import concurrent.futures, hashlib, html.parser, json, re, time, urllib.request
ROOT=Path('/data/xuancheng/agent_overnight_20261020/method_graph_loop_20261020')
ROOT.mkdir(exist_ok=True); OUT=ROOT/'sources'; OUT.mkdir(exist_ok=True)
SOURCES=[
('fs_morph','official_tutorial','https://surfer.nmr.mgh.harvard.edu/fswiki/FsTutorial/MorphAndRecon'),
('fs_parcstats','official_documentation','https://www.freesurfer.net/fswiki/parcstats'),
('fs_lgi','official_documentation','https://surfer.nmr.mgh.harvard.edu/fswiki/LGI'),
('fs_samseg','official_documentation','https://surfer.nmr.mgh.harvard.edu/fswiki/Samseg'),
('fsl_vbm','official_documentation','https://fsl.fmrib.ox.ac.uk/fsl/docs/structural/fslvbm.html'),
('cat','author_documentation','https://neuro-jena.github.io/cat/'),
('macapype_commands','author_documentation','https://macatools.github.io/macapype/command.html'),
('nmt','official_resource','https://afni.nimh.nih.gov/pub/dist/doc/htmldoc/nonhuman/macaque_tempatl/template_nmtv2.html'),
('civet_macaque','primary_paper','https://pmc.ncbi.nlm.nih.gov/articles/PMC7615896/'),
('crossspecies_msm','primary_paper','https://pmc.ncbi.nlm.nih.gov/articles/PMC7180052/'),
('nibabel_fs','author_api','https://nipy.org/nibabel/reference/nibabel.freesurfer.html'),
('trimesh_triangles','author_api','https://trimesh.org/trimesh.triangles.html'),
('ants_thickness','author_source','https://raw.githubusercontent.com/ANTsX/ANTs/main/Scripts/antsCorticalThickness.sh'),
('andy_roi','author_tutorial','https://andysbrainbook.readthedocs.io/en/latest/FreeSurfer/FS_ShortCourse/FS_11_ROIAnalysis.html'),
('andy_failures','author_tutorial','https://andysbrainbook.readthedocs.io/en/latest/FreeSurfer/FS_ShortCourse/FS_12_FailureModes.html'),
('alex_samseg','personal_tutorial','https://alexbrain.cn/?p=840'),
('alex_hcp','personal_tutorial','https://alexbrain.cn/?p=820'),
('reflexion','primary_paper','https://arxiv.org/abs/2303.11366'),
('codeact','primary_paper','https://arxiv.org/abs/2402.01030'),
('reflexion_code','author_source','https://raw.githubusercontent.com/noahshinn/reflexion/main/README.md'),
('codeact_code','author_source','https://raw.githubusercontent.com/xingyaoww/code-act/main/README.md')]
class Text(html.parser.HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.skip=0;self.parts=[]
 def handle_starttag(self,t,a):
  if t in ['script','style','noscript']:self.skip+=1
  if t in ['p','div','li','h1','h2','h3','h4','pre','br','dt','dd','tr']:self.parts.append('\n')
 def handle_endtag(self,t):
  if t in ['script','style','noscript']:self.skip=max(0,self.skip-1)
  if t in ['p','li','h1','h2','h3','h4','pre','dd','tr']:self.parts.append('\n')
 def handle_data(self,s):
  if not self.skip:self.parts.append(s)
def collect(entry):
 key,strength,url=entry;rec={'id':key,'url':url,'evidence_class':strength,'attempts':[]}
 for attempt in range(2):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (source-linked academic method study)'})
   with urllib.request.urlopen(req,timeout=22)as response:raw=response.read(3000001);resolved=response.url
   assert len(raw)<=3000000
   decoded=raw.decode('utf-8','replace')
   if '<html'in decoded[:5000].lower() or '<!doctype html'in decoded[:1000].lower():
    p=Text();p.feed(decoded);text='\n'.join(re.sub(r'\s+',' ',x).strip()for x in ''.join(p.parts).splitlines()if x.strip())
   else:text=decoded
   assert len(text)>250,'No substantial source text'
   (OUT/(key+'.raw')).write_bytes(raw);(OUT/(key+'.txt')).write_text(text,encoding='utf-8')
   rec.update(status='downloaded',resolved_url=resolved,raw_sha256=hashlib.sha256(raw).hexdigest(),text_sha256=hashlib.sha256(text.encode()).hexdigest(),text_chars=len(text),fetched_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()));return rec
  except Exception as e:rec['attempts'].append({'attempt':attempt+1,'error_type':type(e).__name__,'error':str(e)[:400]});time.sleep(1)
 rec['status']='failed';return rec
if __name__=='__main__':
 assert not(ROOT/'source_manifest.json').exists(),'Do not overwrite provenance'
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:records=list(pool.map(collect,SOURCES))
 (ROOT/'source_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
 print(json.dumps([{k:r.get(k)for k in ['id','status','text_chars','attempts']}for r in records],ensure_ascii=False,indent=2))

