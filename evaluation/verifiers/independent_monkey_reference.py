"""Independent binary reference; never mounted to or read by the generation Agent."""
import pathlib,struct,json,hashlib,math,statistics,time
R=pathlib.Path('/data/xuancheng/agent_overnight_20261020');B=pathlib.Path('/data/xuancheng/featurize_20261011/data/KM002/KM002')
def geom(p):
 with p.open('rb') as f:
  magic=int.from_bytes(f.read(3),'big');assert magic==16777214,('unsupported surface format',magic)
  stamp=f.readline().decode(errors='replace').strip();f.readline();nv,nf=struct.unpack('>2i',f.read(8));assert 0<nv<1000000 and 0<nf<3000000
  coords=list(struct.iter_unpack('>3f',f.read(12*nv)));faces=list(struct.iter_unpack('>3i',f.read(12*nf)))
 return coords,faces,stamp

def morph(p):
 with p.open('rb') as f:
  magic=int.from_bytes(f.read(3),'big');assert magic==16777215,('unsupported morph format',magic)
  nv,nf,dim=struct.unpack('>3i',f.read(12));assert dim==1;v=list(struct.unpack('>'+str(nv)+'f',f.read(4*nv)))
 return v,nf

def label(p):
 lines=p.read_text().splitlines();n=int(lines[1]);vs=[int(s.split()[0]) for s in lines[2:] if s.strip()];assert n==len(vs);return set(vs)

def annotation(p):
 raw=p.read_bytes();nv=struct.unpack_from('>i',raw)[0];pairs=list(struct.iter_unpack('>2i',raw[4:4+8*nv]));assert len({a for a,b in pairs})==nv
 return dict(pairs)

def stats(p):
 col=None;out={};meta=[]
 for line in p.read_text().splitlines():
  if line.startswith('# ColHeaders'):col=line.split()[2:]
  elif line and not line.startswith('#'):
   vals=line.split();out[vals[0]]=dict(zip(col,vals))
  elif line.startswith('# Measure'):meta.append(line)
 return {'regions':out,'measures':meta}

def summarise(v):
 good=[x for x in v if math.isfinite(x)]
 return {'n':len(v),'nonfinite':len(v)-len(good),'zero':sum(x==0 for x in good),'negative':sum(x<0 for x in good),'positive':sum(x>0 for x in good),'mean_finite':statistics.fmean(good) if good else None,'median_finite':statistics.median(good) if good else None,'min_finite':min(good) if good else None,'max_finite':max(good) if good else None,'sample_sd_finite':statistics.stdev(good) if len(good)>1 else None}
report={'created':time.time(),'scope':'Independent binary-format geometry/morphometry integrity reference; not anatomical QC or species/scale approval','reference_implementation':'stdlib big-endian struct decoder; independent from model-generated NiBabel calls','hemispheres':{}}
for hemi in ['lh','rh']:
 files={n:B/'surf'/(hemi+'.'+n) for n in ['white','pial','thickness']};c,faces,stamp=geom(files['white']);pc,pf,ps=geom(files['pial']);v,nf=morph(files['thickness']);mask=label(B/'label'/(hemi+'.cortex.label'));annot=annotation(B/'label'/(hemi+'.aparc.annot'))
 area=[0.0]*len(c);invalid=0
 for a,b,z in faces:
  if min(a,b,z)<0 or max(a,b,z)>=len(c):invalid+=1;continue
  u=[c[b][i]-c[a][i] for i in range(3)];w=[c[z][i]-c[a][i] for i in range(3)]
  cross=(u[1]*w[2]-u[2]*w[1],u[2]*w[0]-u[0]*w[2],u[0]*w[1]-u[1]*w[0]);one_third_area=math.sqrt(sum(k*k for k in cross))/6
  for k in [a,b,z]:area[k]+=one_third_area
 h={'white_vertices':len(c),'white_faces':len(faces),'pial_vertices':len(pc),'pial_faces':len(pf),'same_face_topology':faces==pf,'thickness_values':len(v),'white_coordinate_nonfinite':sum(not math.isfinite(k) for xyz in c for k in xyz),'invalid_faces':invalid,'cortex_vertices':len(mask),'annotation_vertices':len(annot),'annotation_nonzero':sum(x!=0 for x in annot.values()),'thickness_all_vertices':summarise(v),'thickness_cortex':summarise([v[k] for k in sorted(mask)]),'white_area_all':sum(area),'white_area_cortex_vertex_mass_lumped':sum(area[k] for k in mask),'coordinate_range':[[min(x[i] for x in c),max(x[i] for x in c)] for i in range(3)],'surface_stamp':stamp,'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files.values()},'stats':stats(B/'stats'/(hemi+'.aparc.stats'))}
 report['hemispheres'][hemi]=h
O=R/'independent_references';O.mkdir(exist_ok=True);(O/'monkey_binary_reference.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:{m:v for m,v in x.items() if m not in ['stats','source_hashes']} for k,x in report['hemispheres'].items()},indent=2))
