"""Decoder tests use tiny synthetic images only; never count as scientific analysis."""
import pathlib,tempfile,struct,gzip,math,array,sys,json
from independent_nifti_pve import decode_pve,check_probability_triplet
checks=[]
def fixture(p,vals,endian='<',slope=1.0,inter=0.0,unit=2,spacing=0.5):
 h=bytearray(352);struct.pack_into(endian+'i',h,0,348);struct.pack_into(endian+'8h',h,40,3,len(vals),1,1,1,1,1,1);struct.pack_into(endian+'2h',h,70,16,32);struct.pack_into(endian+'8f',h,76,1,spacing,spacing,spacing,1,1,1,1);struct.pack_into(endian+'3f',h,108,352,slope,inter);h[123]=unit;struct.pack_into(endian+'h',h,254,1)
 for i,offset in enumerate((280,296,312)):
  row=[0.,0.,0.,0.];row[i]=spacing;struct.pack_into(endian+'4f',h,offset,*row)
 h[344:348]=b'n+1\0';raw=bytes(h)+struct.pack(endian+str(len(vals))+'f',*vals)
 if p.name.endswith('.gz'):
  with gzip.open(p,'wb')as f:f.write(raw)
 else:p.write_bytes(raw)
with tempfile.TemporaryDirectory()as t:
 root=pathlib.Path(t)
 for endian in ['<','>']:
  for ext in ['.nii','.nii.gz']:
   p=root/('fixture'+ext);fixture(p,[0.,0.25,0.5,1.],endian);a,m=decode_pve(p);assert list(a)==[0.,0.25,0.5,1.]and m['pve_sum_voxels']==1.75 and m['pve_volume_mm3']==0.21875 and m['sform_pixdim_volume_agree'];checks.append('endian/compression:'+endian+ext)
 p=root/'scaling.nii';fixture(p,[0.,0.25,0.5],slope=2,inter=0.25);a,m=decode_pve(p);assert list(a)==[0.25,0.75,1.25]and m['pve_sum_voxels']==2.25;checks.append('slope+intercept')
 p=root/'zero_slope.nii';fixture(p,[0.25],slope=0,inter=99);a,m=decode_pve(p);assert a[0]==0.25;checks.append('zero slope ignores intercept')
 for unit,spacing,volume in [(1,.001,1.0),(2,1.0,1.0),(3,1000.,1.0)]:
  p=root/'unit.nii';fixture(p,[1.],unit=unit,spacing=spacing);a,m=decode_pve(p);assert abs(m['voxel_volume_mm3']-volume)<2e-7;checks.append('unit:'+str(unit))
 p=root/'unknown_units.nii';fixture(p,[1.],unit=0);a,m=decode_pve(p);assert m['voxel_volume_mm3']is None and m['pve_volume_mm3']is None;checks.append('unknown units not assumed mm')
 p=root/'nonfinite.nii';fixture(p,[float('nan')]);a,m=decode_pve(p);assert not m['finite']and m['pve_sum_voxels']is None;checks.append('nonfinite preserved as fail')
 p=root/'short.nii';fixture(p,[1.]);p.write_bytes(p.read_bytes()[:-1])
 try:decode_pve(p);raise AssertionError('truncation accepted')
 except ValueError:checks.append('truncated payload rejected')
 p=root/'unsupported.nii';fixture(p,[1.]);raw=bytearray(p.read_bytes());struct.pack_into('<h',raw,70,4);p.write_bytes(raw)
 try:decode_pve(p);raise AssertionError('int PVE accepted')
 except ValueError:checks.append('unsupported dtype explicit')

 def triplet(vals):
  arrays=[];meta=[]
  for i,values in enumerate(vals):
   p=root/('triplet_'+str(i)+'.nii');fixture(p,values);a,m=decode_pve(p);arrays.append(a);meta.append(m)
  return arrays,meta
 a,m=triplet([[0.,0.],[0.,0.],[0.,0.]])
 q=check_probability_triplet(a,m);assert not q['pass']and not q['all_tissues_nonempty']and q['union_support_voxels']==0;checks.append('all-zero PVEs never accepted as successful segmentation')
 a,m=triplet([[0.,.25,0.],[0.,.5,.25],[0.,.25,.75]])
 q=check_probability_triplet(a,m);assert q['pass']and q['union_support_voxels']==2;checks.append('valid partial volumes with outside-brain zeros')
 m[1]['qform_quaternion_offset'][0]=.1;assert not check_probability_triplet(a,m)['same_encoded_grid'];checks.append('qform fields compared, not just codes')
 a,m=triplet([[0.,0.],[.5,.5],[.5,.5]])
 assert not check_probability_triplet(a,m)['pass'];checks.append('missing entire tissue class rejected')
 a,m=triplet([[float('nan')],[.5],[.5]])
 assert not check_probability_triplet(a,m)['pass'];checks.append('nonfinite probabilities fail without fake zero values')
 p=root/'nan_geometry.nii';fixture(p,[1.]);raw=bytearray(p.read_bytes());struct.pack_into('<f',raw,280,float('nan'));p.write_bytes(raw)
 try:decode_pve(p);raise AssertionError('nonfinite geometry accepted')
 except ValueError:checks.append('nonfinite geometry rejected before JSON audit')
 result={'passed':len(checks),'checks':checks,'fixtures_only':True,'not_actual_PVE_analysis':True};print(json.dumps(result,indent=2))
