"""Private independent NIfTI-1 PVE decoder, based on official NIMH field offsets.
Not an analysis implementation and never mounted to the generating Agent.
"""
import array,gzip,hashlib,math,pathlib,struct,sys
SPEC='https://nifti.nimh.nih.gov/nifti-1/documentation/nifti1fields.html'
def decode_pve(path,max_voxels=128000000):
 p=pathlib.Path(path)
 if p.is_symlink()or not p.is_file():raise ValueError('Reference only reads regular image files')
 opener=gzip.open if p.name.endswith('.gz')else open
 with opener(p,'rb')as f:
  h=f.read(348)
  if len(h)!=348:raise ValueError('Short NIfTI header')
  endian='<'if struct.unpack_from('<i',h,0)[0]==348 else '>'if struct.unpack_from('>i',h,0)[0]==348 else None
  if not endian or h[344:348]!=b'n+1\0':raise ValueError('Only single-file NIfTI-1 supported; no silent format substitution')
  dims=struct.unpack_from(endian+'8h',h,40);nd=dims[0]
  if not 3<=nd<=7 or any(x!=1 for x in dims[4:nd+1]):raise ValueError('PVE must be a 3D scalar image')
  shape=list(dims[1:4]);n=math.prod(shape)
  if any(x<=0 for x in shape)or not 0<n<=max_voxels:raise ValueError('Invalid or unbounded image shape')
  dtype,bits=struct.unpack_from(endian+'2h',h,70);typ={16:('f',32),64:('d',64)}.get(dtype)
  if not typ or bits!=typ[1]:raise ValueError('PVE reference supports float32/float64; unsupported types fail explicitly')
  offset=struct.unpack_from(endian+'f',h,108)[0]
  if not math.isfinite(offset)or offset<352 or offset!=int(offset):raise ValueError('Invalid image offset')
  slope,inter=struct.unpack_from(endian+'2f',h,112)
  if slope==0:slope,inter=1.0,0.0
  if not math.isfinite(slope)or not math.isfinite(inter):raise ValueError('Non-finite NIfTI scaling is not silently accepted')
  pix=struct.unpack_from(endian+'8f',h,76);units=h[123]&7
  factor={1:1000.0,2:1.0,3:0.001}.get(units)
  if any(not math.isfinite(x)or x<=0 for x in pix[1:4]):raise ValueError('Invalid voxel spacing')
  voxel=math.prod(pix[1:4])*(factor**3)if factor is not None else None
  qcode,scode=struct.unpack_from(endian+'2h',h,252);srows=[list(struct.unpack_from(endian+'4f',h,off))for off in(280,296,312)]
  qform_values=list(struct.unpack_from(endian+'6f',h,256));qfac=pix[0]
  if not all(math.isfinite(x)for row in srows for x in row)or not all(math.isfinite(x)for x in qform_values+[qfac]):raise ValueError('Non-finite encoded geometry rejected')
  if voxel is not None and(not math.isfinite(voxel)or voxel<=0):raise ValueError('Invalid physical voxel volume')
  a,b,c=(row[:3]for row in srows);det=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
  sform_volume=abs(det)*(factor**3)if scode>0 and factor is not None else None
  f.seek(int(offset));raw=f.read(n*(bits//8))
  if len(raw)!=n*(bits//8):raise ValueError('Truncated image payload')
 values=array.array(typ[0]);values.frombytes(raw)
 if (sys.byteorder=='little')!=(endian=='<'):values.byteswap()
 if slope!=1.0 or inter!=0.0:values=array.array('d',(float(x)*slope+inter for x in values))
 finite=all(math.isfinite(v)for v in values)
 total=math.fsum(values)if finite else None
 metadata={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'shape':shape,'datatype':dtype,'bitpix':bits,'endianness':endian,'scaling':[slope,inter],'pixdim':list(pix[1:4]),'spatial_unit_code':units,'voxel_volume_mm3':voxel,'qform_code':qcode,'sform_code':scode,'qform_quaternion_offset':qform_values,'qfac':qfac,'sform_rows':srows,'sform_voxel_volume_mm3':sform_volume,'sform_pixdim_volume_agree':(abs(sform_volume-voxel)<=max(1e-12,abs(voxel)*1e-6))if sform_volume is not None else None,'finite':finite,'min':min(values)if finite else None,'max':max(values)if finite else None,'pve_sum_voxels':total,'pve_volume_mm3':total*voxel if total is not None and voxel is not None else None,'header_spec':SPEC,'decoder':'stdlib struct+array; compensated math.fsum, independent of model-generated reader and NumPy reductions'}
 return values,metadata


def check_probability_triplet(arrays,metadata,eps=1e-6,mass_eps=1e-4):
 """Private arithmetic prerequisites, never expert anatomy/brain-support QA."""
 if len(arrays)!=3 or len(metadata)!=3:raise ValueError('Exactly3 tissue images required')
 grid_keys=('shape','pixdim','sform_rows','qform_code','sform_code','qform_quaternion_offset','qfac')
 same=all(all(m.get(k)==metadata[0].get(k)for k in grid_keys)for m in metadata)
 same=same and len({len(a)for a in arrays})==1
 probs=all(m['finite']and m['min']>=-eps and m['max']<=1+eps for m in metadata)
 positive=[sum(v>0 for v in a)if m['finite']else 0 for a,m in zip(arrays,metadata)]
 nonempty=all(x>0 for x in positive)
 mass_bad=None;max_dev=None;union=None
 if probs and same:
  mass_bad=0;max_dev=0.0;union=0
  for vals in zip(*arrays):
   total=math.fsum(vals);dev=min(abs(total),abs(total-1));mass_bad+=dev>mass_eps;max_dev=max(max_dev,dev);union+=total>eps
 physical=all(m['voxel_volume_mm3']is not None and m['sform_pixdim_volume_agree']is True for m in metadata)
 return {'same_encoded_grid':same,'finite_in_declared_probability_range':probs,
   'positive_voxels_per_tissue':positive,'all_tissues_nonempty':nonempty,
   'union_support_voxels':union,'mass_not_near_zero_or_one_voxels':mass_bad,
   'max_mass_deviation_to_zero_or_one':max_dev,
   'physical_units_and_sform_volume_supported':physical,
   'pass':same and probs and nonempty and union is not None and union>0 and mass_bad==0 and physical,
   'input_brain_extraction_support_and_anatomical_quality':'Nonempty encoded PVE support only. Alignment/completeness against the actual brain input and anatomical segmentation still require separate source/image review.'}
