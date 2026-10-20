#!/usr/bin/env python3
"""Assemble an independent AFNI/C3D runtime from verified official archives.

Run inside the read-only Ubuntu 22.04 PrimateX image to snapshot a consistent
glibc/loader family. No PrimateX/FSL/ANTs/FreeSurfer tools are copied.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

BASE = Path('/data/xuancheng/structural_env')
STAGE = BASE / 'cache/structural_afni'
ROOT = STAGE / 'rootfs'
AFNI = STAGE / 'package/linux_rocky_8'
C3D = BASE / 'cache/structural_c3d/package/c3d-1.4.4-Linux-gcc64'
EXTRA = STAGE / 'rpmroot'
if ROOT.exists():
    raise SystemExit('Refusing to replace existing rootfs: ' + str(ROOT))
ROOT.mkdir()
for p in ['usr/bin', 'usr/lib', 'usr/lib64', 'etc', 'tmp', 'var/tmp', 'proc',
          'sys', 'dev', 'run', 'data', 'opt', 'usr/share/licenses']:
    (ROOT / p).mkdir(parents=True, exist_ok=True)
for link, target in [('bin', 'usr/bin'), ('lib', 'usr/lib'), ('lib64', 'usr/lib64')]:
    (ROOT / link).symlink_to(target)
shutil.copytree(AFNI, ROOT / 'opt/afni/bin')
shutil.copytree(C3D, ROOT / 'opt/c3d')
if EXTRA.exists():
    shutil.copytree(EXTRA, ROOT, dirs_exist_ok=True, symlinks=True)

files = []
packages = set()
def digest(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def copy_runtime(src, dest=None):
    src = Path(src)
    if not src.exists():
        return
    if dest is None:
        dest = src
    dest = Path(dest)
    dst = ROOT / str(dest).lstrip('/')
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        dst.unlink()
    if not dst.exists():
        shutil.copy2(src, dst, follow_symlinks=True)
    record = {'source': str(src), 'image_path': str(dest), 'sha256': digest(dst)}
    q = subprocess.run(['dpkg-query', '-S', str(src.resolve())], capture_output=True, text=True)
    if q.returncode == 0:
        owner = q.stdout.split(': /', 1)[0].strip()
        record['dpkg_package'] = owner
        packages.add(owner)
    files.append(record)

commands = '''bash sh tcsh env cat cp mv rm mkdir rmdir ls chmod ln readlink
pwd basename dirname grep egrep fgrep awk sed sort uniq cut head tail tr wc
date sleep touch tee gzip gunzip tar find xargs printf nice kill hostname pkill pgrep ldd
uname bc file which tput timeout stat dd od expr paste seq mktemp ps id'''.split()
missing_commands = []
system_execs = []
for name in commands:
    p = shutil.which(name, path='/usr/bin:/bin')
    if p:
        copy_runtime(p, '/usr/bin/' + name)
        system_execs.append(Path(p))
    else:
        missing_commands.append(name)
copy_runtime('/usr/bin/python3.10', '/usr/bin/python3.10')
(ROOT / 'usr/bin/python3').symlink_to('python3.10')
(ROOT / 'usr/bin/python').symlink_to('python3.10')
shutil.copytree('/usr/lib/python3.10', ROOT / 'usr/lib/python3.10',
                ignore=shutil.ignore_patterns('__pycache__', 'site-packages', 'dist-packages'))
system_execs.append(Path('/usr/bin/python3.10'))
for p in ['/etc/os-release', '/etc/nsswitch.conf', '/etc/passwd', '/etc/group',
          '/usr/share/zoneinfo/UTC', '/etc/services', '/usr/share/misc/magic.mgc']:
    copy_runtime(p)
for p in ['/etc/fonts', '/usr/share/fonts', '/usr/share/X11', '/usr/share/terminfo',
          '/lib/terminfo']:
    if Path(p).exists():
        shutil.copytree(p, ROOT / p.lstrip('/'), dirs_exist_ok=True, symlinks=True)

env = dict(os.environ)
env['LD_LIBRARY_PATH'] = ':'.join([str(EXTRA / 'usr/lib64'), str(AFNI),
                                 '/usr/lib/x86_64-linux-gnu', '/lib/x86_64-linux-gnu'])
missing_libraries = {}
def elf(p):
    try:
        with open(p, 'rb') as f:
            return f.read(4) == b'\x7fELF'
    except (OSError, IsADirectoryError):
        return False

elfs = [p for p in AFNI.iterdir() if elf(p)]
elfs += [p for p in C3D.glob('bin/*') if elf(p)]
elfs += system_execs
elfs += [p for p in Path('/usr/lib/python3.10/lib-dynload').glob('*.so')]
selected_extra = ['Xvfb', 'xkbcomp', 'pnmcat', 'pnmcut', 'pnmtopng', 'ppmtopng',
                  'pamcat', 'pamcut', 'pamtopng', 'pnmscale', 'pnmtojpeg']
for name in selected_extra:
    p = EXTRA / 'usr/bin' / name
    if p.exists():
        elfs.append(p)
for p in (EXTRA / 'usr/lib64').glob('*.so*'):
    if elf(p):
        elfs.append(p)
for p in elfs:
    result = subprocess.run(['/usr/bin/ldd', str(p)], capture_output=True, text=True, env=env)
    out = result.stdout + result.stderr
    missing = re.findall(r'^\s*(\S+) => not found', out, re.M)
    if missing:
        missing_libraries[str(p)] = missing
    for name, source in re.findall(r'^\s*(\S+) => (/\S+)', out, re.M):
        source = Path(source)
        if str(source).startswith(str(AFNI)):
            continue
        if str(source).startswith(str(EXTRA)):
            continue
        # Keep the Ubuntu library family, including the canonical loader path.
        copy_runtime(source)
    for source in re.findall(r'^\s*(/\S+) \(', out, re.M):
        copy_runtime(source)

# dlopen-only glibc libraries (name service resolution etc.).
for p in Path('/lib/x86_64-linux-gnu').glob('libnss_*.so*'):
    copy_runtime(p)
for name in sorted(packages):
    package = name.split(':', 1)[0]
    source = Path('/usr/share/doc') / package / 'copyright'
    if source.exists():
        copy_runtime(source, '/usr/share/licenses/ubuntu/' + package + '.copyright')
for source, name in [(STAGE / 'AFNI_LICENSE.txt', 'AFNI_LICENSE.txt'),
                     (BASE / 'cache/structural_c3d/C3D_COPYING.txt', 'C3D_COPYING.txt')]:
    copy_runtime(source, '/usr/share/licenses/' + name)
version = subprocess.run(['dpkg-query', '-W', '-f=${Package}\t${Version}\n'] + sorted(packages),
                         capture_output=True, text=True).stdout
report = {
    'source_image': '/data/xuancheng/agent/PrimateX_1_7.sif',
    'source_userspace': 'Ubuntu 22.04.5',
    'scope': 'Only OS runtime libraries and shell/Python/coreutils; no neuroimaging tools from source SIF',
    'runtime_files': files,
    'dpkg_versions': version,
    'missing_libraries': missing_libraries,
    'missing_commands': missing_commands,
    'unvalidated_features': ['C3D GUI', 'AFNI R-based statistics', 'full real MRI @animal_warper pipeline']
}
(STAGE / 'runtime-report.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'rootfs': str(ROOT), 'copied_runtime_files': len(files),
                  'missing_libraries': missing_libraries, 'missing_commands': missing_commands}, indent=2))
