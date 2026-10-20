"""Private independent raw FreeSurfer decoder and explicit coordinate references.
Based on pinned NiBabel5.4.2 fs/io.py and mghformat.py, implemented with stdlib.
Never mounted/exposed to generating Agent. No implicit data-analysis execution.
"""
import struct,array,math,gzip,sys,pathlib,hashlib

def digest(p):
 with pathlib.Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read_array(f,code,n):
 a=array.array(code);raw=f.read(n*a.itemsize)
 if len(raw)!=n*a.itemsize:raise ValueError('Truncated binary data')
 a.frombytes(raw)
 if sys.byteorder=='little'and a.itemsize>1:a.byteswap()
 return a

def f32(x):return struct.unpack('>f',struct.pack('>f',x))[0]

def geometry_from_fields(shape,delta,mdc,center):
 if len(shape)!=3 or any(n<=0 for n in shape)or any(not math.isfinite(x)or x<=0 for x in delta):raise ValueError('Invalid volume grid')
 # File Mdc stores each voxel axis direction as a row; scanner affine has them as columns.
 A=[[float(mdc[c][r])*float(delta[c])for c in range(3)]for r in range(3)]
 scanner=[A[r]+[float(center[r])-math.fsum(A[r][c]*shape[c]/2 for c in range(3))]for r in range(3)]+[[0.,0.,0.,1.]]
 centers=[f32(shape[i]*delta[i]/2)for i in range(3)]
 tkr=[[-delta[0],0.,0.,centers[0]],[0.,0.,delta[2],-centers[2]],[0.,-delta[1],0.,centers[1]],[0.,0.,0.,1.]]
 if not all(math.isfinite(x)for row in scanner for x in row):raise ValueError('Nonfinite affine')
 return scanner,tkr

def raw_mgh(p,load_data=False):
 opener=gzip.open if str(p).endswith('.mgz')else open
 with opener(p,'rb')as f:
  h=f.read(284)
  if len(h)!=284:raise ValueError('Truncated MGH header')
  version,nx,ny,nz,nf,typ,dof=struct.unpack_from('>7i',h)
  if version!=1 or nf!=1 or not 0<nx*ny*nz<=128000000 or typ not in [0,1,3,4]:raise ValueError('Unsupported MGH format or dimensions')
  ras=struct.unpack_from('>h',h,28)[0]
  if not ras:raise ValueError('No valid RAS geometry: do not invent defaults')
  delta=struct.unpack_from('>3f',h,30);flat=struct.unpack_from('>9f',h,42);mdc=[list(flat[i:i+3])for i in range(0,9,3)];center=struct.unpack_from('>3f',h,78);shape=[nx,ny,nz]
  scanner,tkr=geometry_from_fields(shape,delta,mdc,center)
  meta={'sha256':digest(p),'shape':shape,'type':typ,'delta':list(delta),'Mdc_rows':mdc,'Pxyz_c':list(center),'scanner_vox2ras':scanner,'tkr_vox2ras':tkr,'RAS_flag':bool(ras),'unit_basis':'MGH software format convention, not reviewed acquisition provenance'}
  data=read_array(f,{0:'B',1:'i',3:'f',4:'h'}[typ],nx*ny*nz)if load_data else None
 return data,meta

def raw_surface(p):
 with open(p,'rb')as f:
  if f.read(3)!=b'\xff\xff\xfe':raise ValueError('Only triangle geometry accepted')
  stamp=f.readline().rstrip(b'\n').decode('utf-8');blank=f.readline()
  raw=f.read(8)
  if len(raw)!=8:raise ValueError('Missing mesh dimensions')
  nv,nf=struct.unpack('>2i',raw)
  if not 0<nv<10000000 or not 0<nf<20000000:raise ValueError('Invalid mesh dimensions')
  coord=read_array(f,'f',3*nv);faces=read_array(f,'i',3*nf)
  if not all(math.isfinite(x)for x in coord)or any(x<0 or x>=nv for x in faces):raise ValueError('Nonfinite coordinate or invalid triangle index')
  footer=f.read();meta={};parse='absent'
  if footer:
   import io
   ff=io.BytesIO(footer);head=ff.read(4)
   if len(head)==4:
    i=struct.unpack('>i',head)[0];head=[i]if i==20 else [i,*struct.unpack('>2i',ff.read(8))]if len(footer)>=12 else [i]
    if head in [[20],[2,0,20]]:
     parse='present';meta['head']=head
     for key in ['valid','filename','volume','voxelsize','xras','yras','zras','cras']:
      pair=ff.readline().decode('utf-8').split('=',1)
      if len(pair)!=2 or pair[0].strip()!=key:raise ValueError('Malformed surface volume_info')
      value=pair[1].strip();meta[key]=value if key in ['valid','filename']else[(int(x)if key=='volume'else float(x))for x in value.split()]
    else:parse='unknown_extension'
  return coord,faces,{'sha256':digest(p),'n_vertices':nv,'n_faces':nf,'stamp':stamp,'volume_info':meta,'volume_info_status':parse,'footer_sha256':hashlib.sha256(footer).hexdigest()}

def cortex_label(p,nv):
 lines=pathlib.Path(p).read_text().splitlines()
 if len(lines)<2:raise ValueError('Missing cortex label header')
 n=int(lines[1]);rows=[s.split()for s in lines[2:]if s.strip()]
 if len(rows)!=n:raise ValueError('Cortex label length mismatch')
 ids=[int(r[0])for r in rows]
 if len(set(ids))!=n or any(i<0 or i>=nv for i in ids):raise ValueError('Cortex indices invalid or duplicated')
 return set(ids)

def tkr_to_voxel(point,meta):
 # Analytic inverse, independent of model's np.linalg.inv/apply_affine.
 t=meta['tkr_vox2ras'];x,y,z=point;d=meta['delta']
 return[(t[0][3]-x)/d[0],(t[2][3]-z)/d[1],(y-t[1][3])/d[2]]

def apply(M,p):return[math.fsum(M[r][c]*p[c]for c in range(3))+M[r][3]for r in range(3)]

def grid_value(data,shape,ijk):
 if not all(isinstance(i,int)and 0<=i<n for i,n in zip(ijk,shape)):return None
 i,j,k=ijk;return data[i+shape[0]*(j+shape[1]*k)]

def nearest(data,shape,p,rounding='half_up'):
 if not all(math.isfinite(x)for x in p):return None,None
 if rounding=='half_up':q=[math.floor(x+.5)for x in p]
 elif rounding=='ties_even':q=[round(x)for x in p]
 else:raise ValueError('Unknown rounding convention')
 return q,grid_value(data,shape,q)

def trilinear(data,shape,p):
 if not all(math.isfinite(x)and 0<=x<=n-1 for x,n in zip(p,shape)):return None
 low=[math.floor(x)for x in p];high=[min(i+1,n-1)for i,n in zip(low,shape)];w=[x-i for x,i in zip(p,low)]
 return math.fsum(grid_value(data,shape,[high[0]if a else low[0],high[1]if b else low[1],high[2]if c else low[2]])*(w[0]if a else 1-w[0])*(w[1]if b else 1-w[1])*(w[2]if c else 1-w[2])for a in [0,1]for b in [0,1]for c in [0,1])
