"""Synthetic FastSurfer layout; no real imaging or subject information."""
from pathlib import Path
import tempfile
import unittest
from backend.analysis_input_links import resolve_input
from backend.analysis_profile_worker import profile_file, value
from backend.analysis_atlas_identity import identify

class FastSurferLayoutTests(unittest.TestCase):
    def test_completion_marker_and_log(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'stats').mkdir();(p/'scripts').mkdir()
            (p/'stats/lh.aparc.DKTatlas.mapped.stats').write_text('# synthetic\n')
            (p/'scripts/recon-surf.done').write_text('done')
            (p/'scripts/recon-surf.log').write_text('finished\n')
            recon=value(profile_file(p/'stats/lh.aparc.DKTatlas.mapped.stats')['recon'])
            self.assertTrue(value(recon['done']))
            self.assertEqual(value(recon['completion_marker']),'recon-surf.done')
            self.assertEqual(value(recon['pipeline']),'FastSurfer')
    def test_internal_and_external_links(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'subject';root.mkdir();(root/'surf').mkdir()
            target=root/'surf/lh.pial.T1';target.write_text('synthetic')
            link=root/'surf/lh.pial';link.symlink_to('lh.pial.T1')
            self.assertEqual(resolve_input(link,root),target)
            observed=value(profile_file(link)['link'])
            self.assertEqual(observed['target'],'lh.pial.T1')
            outside=Path(d)/'outside';outside.write_text('no')
            escape=root/'external';escape.symlink_to(outside)
            with self.assertRaisesRegex(ValueError,'outside'):resolve_input(escape,root)
    def test_dkt_mapped_family(self):
        self.assertEqual(identify('aparc.DKTatlas.mapped')['canonical_name'],'DKT')

def test_absolute_link_container_view_is_local(tmp_path):
    from types import SimpleNamespace
    from backend.analysis_input_links import prepare_input_views
    root=tmp_path/'subject';(root/'surf').mkdir(parents=True)
    target=root/'surf/lh.pial.T1';target.write_text('synthetic')
    link=root/'surf/lh.pial';link.symlink_to(target)
    state=tmp_path/'private';state.mkdir()
    executor=SimpleNamespace(input_roots=[root])
    tools=SimpleNamespace(input_roots=[root],executor=executor,control_store=SimpleNamespace(root=state))
    records=prepare_input_views(tools,['/inputs/0/surf/lh.pial'])
    mapped=executor.input_roots[0]/'surf/lh.pial'
    assert mapped.is_symlink() and not mapped.readlink().is_absolute()
    assert mapped.read_text()=='synthetic'
    assert records['/inputs/0/surf/lh.pial']['target']==str(target)
    assert records['/inputs/0/surf/lh.pial']['resolved']=='/inputs/0/surf/lh.pial.T1'
    assert link.readlink()==target
