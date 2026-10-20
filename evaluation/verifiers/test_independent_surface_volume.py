import unittest,tempfile,pathlib,struct,gzip,math
import independent_surface_volume as ref
class IndependentCoordinateFixtures(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.r=pathlib.Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def mesh(self,coords=None,faces=None,footer=b''):
  coords=coords or [0.,0.,0.,1.,0.,0.,0.,1.,0.];faces=faces or [0,1,2];p=self.r/'mesh';p.write_bytes(b'\xff\xff\xfecreated\n\n'+struct.pack('>2i',3,1)+struct.pack('>9f',*coords)+struct.pack('>3i',*faces)+footer);return p
 def test_triangle_big_endian_and_absent_footer(self):
  c,f,m=ref.raw_surface(self.mesh());self.assertEqual(list(c),[0.,0.,0.,1.,0.,0.,0.,1.,0.]);self.assertEqual(list(f),[0,1,2]);self.assertEqual(m['volume_info_status'],'absent')
 def test_both_known_footer_tags(self):
  text=b'valid = 1\nfilename = sample\nvolume = 4 6 8\nvoxelsize = 2 3 5\nxras = 1 0 0\nyras = 0 1 0\nzras = 0 0 1\ncras = 0 0 0\n'
  for tag in [struct.pack('>i',20),struct.pack('>3i',2,0,20)]:
   c,f,m=ref.raw_surface(self.mesh(footer=tag+text));self.assertEqual(m['volume_info']['volume'],[4,6,8]);self.assertEqual(m['volume_info']['voxelsize'],[2.,3.,5.])
 def test_invalid_face_rejected(self):
  with self.assertRaises(ValueError):ref.raw_surface(self.mesh(faces=[0,1,3]))
 def test_nonfinite_mesh_rejected(self):
  with self.assertRaises(ValueError):ref.raw_surface(self.mesh(coords=[math.nan,0.,0.,1.,0.,0.,0.,1.,0.]))
 def test_truncated_mesh_rejected(self):
  p=self.mesh();p.write_bytes(p.read_bytes()[:-4])
  with self.assertRaises(ValueError):ref.raw_surface(p)
 def test_explicit_scanner_and_tkr_distinction(self):
  sc,tk=ref.geometry_from_fields([4,6,8],[2.,3.,5.],[[1,0,0],[0,1,0],[0,0,1]],[0.,0.,0.]);self.assertEqual(tk,[[-2.,0.,0.,4.],[0.,0.,5.,-20.],[0.,-3.,0.,9.],[0.,0.,0.,1.]]);self.assertEqual(ref.apply(sc,[3,2,3]),[2.,-3.,-5.]);self.assertEqual(ref.tkr_to_voxel([-2.,-5.,3.],{'tkr_vox2ras':tk,'delta':[2.,3.,5.]}),[3.,2.,3.])
 def test_mgh_raw_voxel_order_and_geometry(self):
  p=self.r/'test.mgz';h=bytearray(284);struct.pack_into('>7i',h,0,1,2,2,2,1,3,0);struct.pack_into('>h',h,28,1);struct.pack_into('>3f',h,30,1,2,3);struct.pack_into('>9f',h,42,1,0,0,0,1,0,0,0,1);struct.pack_into('>3f',h,78,0,0,0)
  with gzip.open(p,'wb')as f:f.write(h);f.write(struct.pack('>8f',*range(8)))
  d,m=ref.raw_mgh(p,True);self.assertEqual(list(d),list(range(8)));self.assertEqual(ref.grid_value(d,m['shape'],[1,0,1]),5);self.assertEqual(m['scanner_vox2ras'],[[1.,0.,0.,-1.],[0.,2.,0.,-2.],[0.,0.,3.,-3.],[0.,0.,0.,1.]])
 def test_mgh_missing_geometry_rejected(self):
  p=self.r/'bad.mgh';h=bytearray(284);struct.pack_into('>7i',h,0,1,1,1,1,1,0,0);p.write_bytes(h+b'\0')
  with self.assertRaises(ValueError):ref.raw_mgh(p)
 def test_sampling_boundary_NA_and_half_ties(self):
  d=list(range(8));sh=[2,2,2];self.assertEqual(ref.trilinear(d,sh,[.5,.5,.5]),3.5);self.assertIsNone(ref.trilinear(d,sh,[-.1,0,0]));self.assertEqual(ref.nearest(d,sh,[.5,0,0],'half_up'),([1,0,0],1));self.assertEqual(ref.nearest(d,sh,[.5,0,0],'ties_even'),([0,0,0],0));self.assertIsNone(ref.nearest(d,sh,[2,0,0])[1]);self.assertIsNone(ref.grid_value(d,sh,[-1,0,0]));self.assertEqual(ref.trilinear(d,sh,[1,1,1]),7.)
 def test_labels_invalid_index_and_duplicate_rejected(self):
  p=self.r/'cortex.label';p.write_text('# label\n2\n0 0 0 0 0\n0 0 0 0 0\n')
  with self.assertRaises(ValueError):ref.cortex_label(p,3)
if __name__=='__main__':unittest.main(verbosity=2)
