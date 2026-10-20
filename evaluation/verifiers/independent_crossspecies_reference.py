"""Independent reference for four known samples; not exposed to the generation Agent."""
import pathlib,struct,json,math,hashlib,gzip,time
R=pathlib.Path('/data/xuancheng/agent_overnight_20261020')
subjects={sid:pathlib.Path('/data/xuancheng/human_fastsurfer/subjects')/sid for sid in ['100610','101309','101410']};subjects['KM002']=pathlib.Path('/data/xuancheng/featurize_20261011/data/KM002/KM002')
def geometry(p,mask):
 with p.open('rb') as f:
  assert int.from_bytes(f.read(3),'big')==16777214
  stamp=f.readline().decode(errors='replace').strip();f.readline();nv,nf=struct.unpack('>2i',f.read(8));assert 0<nv<1000000 and 0<nf<3000000
  coords=list(struct.iter_unpack('>3f',f.read(12*nv)));raw=f.read(12*nf);total=0.;valid=0;cortex_area=0.;degenerate=0;min_area=float('inf')
  for face in struct.iter_unpack('>3i',raw):
   if min(face)<0 or max(face)>=nv:raise ValueError('Invalid face')
   a,b,c=[coords[i] for i in face];u=[b[k]-a[k] for k in range(3)];v=[c[k]-a[k] for k in range(3)];cx=u[1]*v[2]-u[2]*v[1];cy=u[2]*v[0]-u[0]*v[2];cz=u[0]*v[1]-u[1]*v[0];area=math.sqrt(cx*cx+cy*cy+cz*cz)/2;total+=area;valid+=1;min_area=min(min_area,area);degenerate+=int(area==0)
   if all(v in mask for v in face):cortex_area+=area
  tail=f.read(8192).decode(errors='replace')
 return {'vertices':nv,'faces':nf,'all_white_mesh_area':total,'all_three_vertices_cortex_area':cortex_area,'degenerate_triangles':degenerate,'nondegenerate_triangles':nf-degenerate,'minimum_triangle_area':min_area,'coordinate_finite':all(math.isfinite(x) for xyz in coords for x in xyz),'volume_info_tail':tail,'stamp':stamp,'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
out={'created':time.time(),'algorithm':'Big-endian triangle surface decoder, scalar cross products and full triangle sum; independent from model NiBabel/numpy implementation','scope':'Numerical geometry/index check, not anatomy, population inference or biological comparability','subjects':{}}
for sid,p in subjects.items():
 masks={}
 for hemi in ['lh','rh']:
  lines=(p/'label'/(hemi+'.cortex.label')).read_text().splitlines();ids=[int(x.split()[0]) for x in lines[2:] if x.strip()];assert len(ids)==int(lines[1]);masks[hemi]=set(ids)
 h={hemi:geometry(p/'surf'/(hemi+'.white'),masks[hemi]) for hemi in ['lh','rh']};l=h['lh']['all_white_mesh_area'];r=h['rh']['all_white_mesh_area'];h['AI_2LminusR_over_LplusR']=2*(l-r)/(l+r);h['input_root']=str(p);cl=h['lh']['all_three_vertices_cortex_area'];cr=h['rh']['all_three_vertices_cortex_area'];h['AI_cortex_subset']=2*(cl-cr)/(cl+cr)
 mgz=p/'mri'/'orig.mgz'
 if mgz.is_file() and not mgz.is_symlink():
  with gzip.open(mgz,'rb') as f:raw=f.read(284)
  ver,w,hh,depth,frames,typ,dof=struct.unpack_from('>7i',raw);good=struct.unpack_from('>h',raw,28)[0];h['orig_mgh_header']={'version':ver,'shape':[w,hh,depth,frames],'ras_good':good,'voxel_deltas':list(struct.unpack_from('>3f',raw,30)) if good else None}
 out['subjects'][sid]=h
O=R/'independent_references';O.mkdir(exist_ok=True);(O/'crossspecies_geometry_reference.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({sid:{'vertices':[h[x]['vertices'] for x in ['lh','rh']],'area_lh':h['lh']['all_white_mesh_area'],'area_rh':h['rh']['all_white_mesh_area'],'AI':h['AI_2LminusR_over_LplusR'],'orig_mgh_header':h.get('orig_mgh_header')} for sid,h in out['subjects'].items()},ensure_ascii=False,indent=2))


