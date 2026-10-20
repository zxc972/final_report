"""Independent raw MGH+table reference; never mount this for the generating Agent."""
import pathlib,gzip,struct,array,sys,json,collections,math,hashlib,time
R=pathlib.Path('/data/xuancheng/agent_overnight_20261020');roots={s:pathlib.Path('/data/xuancheng/human_fastsurfer/subjects')/s for s in ['100610','101309','101410']};roots['KM002']=pathlib.Path('/data/xuancheng/featurize_20261011/data/KM002/KM002')
def decode(p):
 with gzip.open(p,'rb') as f:
  h=f.read(284);ver,nx,ny,nz,nf,typ,dof=struct.unpack_from('>7i',h);assert ver==1 and nf==1
  n=nx*ny*nz;good=struct.unpack_from('>h',h,28)[0];assert good
  ds=struct.unpack_from('>3f',h,30);m=struct.unpack_from('>9f',h,42)
  det=m[0]*(m[4]*m[8]-m[5]*m[7])-m[1]*(m[3]*m[8]-m[5]*m[6])+m[2]*(m[3]*m[7]-m[4]*m[6])
  code={0:'B',1:'i',3:'f',4:'h'}[typ];a=array.array(code);a.frombytes(f.read(n*array.array(code).itemsize));assert len(a)==n
  if sys.byteorder=='little' and code!='B':a.byteswap()
  c=collections.Counter(a);assert min(c)>=0 and all(math.isfinite(k) and int(k)==k for k in c);c={int(k):v for k,v in c.items()}
 return {'shape':[nx,ny,nz],'dtype_mgh':typ,'voxel_sizes':list(ds),'direction_determinant':det,'voxel_volume_mm3':abs(math.prod(ds)*det),'counts':{str(k):v for k,v in sorted(c.items())},'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def table(p):
 headers=None;rows=[];measure={};other={}
 for line in p.read_text().splitlines():
  if line.startswith('# ColHeaders'):headers=line.split()[2:]
  elif line.startswith('# Measure '):
   parts=[x.strip() for x in line[len('# Measure '):].split(',')]
   if len(parts)>=5:
    try:measure[parts[1]]={'value':float(parts[-2]),'unit':parts[-1],'source_line':line}
    except ValueError:pass
  elif line.startswith('# cmdline '):other['cmdline']=line
  elif line.strip() and not line.startswith('#'):
   assert headers;values=line.split();assert len(values)==len(headers);rows.append(dict(zip(headers,values)))
 return {'columns':headers,'rows':rows,'measures':measure,**other,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
out={'created':time.time(),'algorithm':'stdlib gzip/struct/array/Counter MGH decoder; independent from NiBabel/numpy, table dynamic ColHeaders','exposed_to_generator':False,'subjects':{}}
for sid,p in roots.items():
 seg=p/'mri'/('aseg.presurf.mgz' if sid=='KM002' else 'aseg.mgz');q=decode(seg);q['path']=str(seg)
 if sid!='KM002':
  t=table(p/'stats'/'aseg.stats');q['stats']=t;q['count_vs_stats']=[{'label':int(r['SegId']),'reference_count':q['counts'].get(r['SegId'],0),'stats_NVoxels':int(r['NVoxels']),'passed':q['counts'].get(r['SegId'],0)==int(r['NVoxels'])} for r in t['rows']]
 out['subjects'][sid]=q
O=R/'independent_references';O.mkdir(exist_ok=True);(O/'segmentation_volume_reference.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({sid:{'shape':x['shape'],'nonzero_labels':len(x['counts'])-int('0' in x['counts']),'stats_rows':len(x.get('stats',{}).get('rows',[])),'count_vs_stats_passed':sum(q['passed'] for q in x.get('count_vs_stats',[]))} for sid,x in out['subjects'].items()},indent=2))

