import pathlib,json,os
import pytest
from test_analysis_executor import _module, SandboxExecutor, GOOD_CHECKS, PROBE_MARKER


def make_executor(tmp_path,license_path,runner=None):
    data=tmp_path/'data';data.mkdir(exist_ok=True)
    runtime=tmp_path/'runtime';(runtime/'bin').mkdir(parents=True,exist_ok=True);(runtime/'bin/python').write_text('fixture')
    image=tmp_path/'fixture.sif';image.write_text('fixture')
    return SandboxExecutor(tmp_path/'work',[data],runtime_env=runtime,runtime_image=image,fs_license_file=license_path,command_runner=runner,platform_name='linux',apptainer_binary='/usr/bin/python3')


def test_runtime_license_single_readonly_mount_and_fixed_environment(tmp_path):
    license_path=tmp_path/'license.txt';license_path.write_text('test-only license placeholder')
    executor=make_executor(tmp_path,license_path);cmd=executor._command(executor.workdir,executor.input_roots,['-c','pass'])
    assert str(license_path)+':/opt/analysis_freesurfer_license.txt:ro' in cmd
    assert 'FS_LICENSE=/opt/analysis_freesurfer_license.txt' in cmd
    assert str(tmp_path)+':/opt' not in cmd
    assert executor._environment()=={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':'/tmp'}


@pytest.mark.parametrize('mode',['empty','oversize','directory','symlink','inside_work'])
def test_invalid_license_path_rejected(tmp_path,mode):
    p=tmp_path/'license.txt'
    if mode=='empty':p.write_text('')
    if mode=='oversize':p.write_bytes(b'x'*16385)
    if mode=='directory':p.mkdir()
    if mode=='symlink':
        target=tmp_path/'real.txt';target.write_text('fixture');p.symlink_to(target)
    if mode=='inside_work':
        p=tmp_path/'work/license.txt';p.parent.mkdir();p.write_text('fixture')
    with pytest.raises((ValueError,IsADirectoryError)):make_executor(tmp_path,p)


def test_runtime_license_change_to_symlink_rechecked(tmp_path):
    p=tmp_path/'license.txt';p.write_text('fixture');executor=make_executor(tmp_path,p)
    p.unlink();q=tmp_path/'target';q.write_text('different fixture');p.symlink_to(q)
    with pytest.raises(ValueError):executor._command(executor.workdir,[],['-c','pass'])


def test_probe_requires_license_readonly_evidence(tmp_path):
    p=tmp_path/'license.txt';p.write_text('fixture')
    def runner(command,**kw):return {'exit_code':0,'stdout':PROBE_MARKER+json.dumps({**GOOD_CHECKS,'freesurfer_license_present':True,'freesurfer_license_readonly':False}),'stderr':''}
    executor=make_executor(tmp_path,p,runner)
    assert executor.probe()['status']=='blocked'
