"""Supplement public PDF tutorials; preserve original collector and failed URLs."""
import json,re,hashlib,urllib.request,subprocess,time
from pathlib import Path
R=Path('/data/xuancheng/agent_overnight_20261020/method_graph_loop_20261020');S=R/'sources'
out=[]
for key in ['alex_samseg','alex_hcp']:
 raw=(S/(key+'.raw')).read_text()
 links=re.findall(r'href=["\']([^"\']+\.pdf)["\']',raw)
 assert links
 from urllib.parse import quote, urlsplit, urlunsplit
 parts=urlsplit(links[0]);url=urlunsplit((parts.scheme,parts.netloc,quote(parts.path,safe='/%'),parts.query,parts.fragment));request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(request,timeout=25)as f:data=f.read(10000001)
 assert data.startswith(b'%PDF')and len(data)<10000000
 pdf=S/(key+'_pdf.pdf');pdf.write_bytes(data)
 txt=S/(key+'_pdf.txt')
 p=subprocess.run(['pdftotext','-layout',str(pdf),str(txt)],capture_output=True,timeout=20)
 assert p.returncode==0 and txt.stat().st_size>500
 out.append({'id':key+'_pdf','url':url,'evidence_class':'personal_tutorial','status':'downloaded','text_chars':len(txt.read_text()),'raw_sha256':hashlib.sha256(data).hexdigest(),'text_sha256':hashlib.sha256(txt.read_bytes()).hexdigest(),'extraction':'pdftotext -layout; no claim of layout inspection or independent biological validation','time':time.time()})
(R/'pdf_source_manifest.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(out,ensure_ascii=False,indent=2))

