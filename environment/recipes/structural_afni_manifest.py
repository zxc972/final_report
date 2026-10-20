#!/usr/bin/env python3
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

base = Path('/data/xuancheng/structural_env')
stage = base / 'cache/structural_afni'
image = base / 'images/afni-c3d.sif'
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

archive_afni = stage / 'linux_rocky_8.tgz'
archive_c3d = base / 'cache/structural_c3d/c3d-1.4.4-Linux-gcc64.tar.gz'
assert sha(archive_afni) == '6b0d2d09bd42a7f50c9501f3dd514ad4d29b0559a4d016953f910ff924ac9485'
assert sha(archive_c3d) == '4930f38ce81b119a375ca416871a597545dd779bf45f22572dcd5e0ea7ce0407'
smoke = json.loads((base / 'tests/afni_c3d/smoke-summary.json').read_text())
assert smoke['status'] == 'passed'
rpms = []
for p in sorted((stage / 'rpms').glob('*.rpm')):
    r = subprocess.run(['/usr/bin/rpm', '--dbpath', str(stage / 'rpms/rpmdb'), '-K', str(p)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    info = subprocess.run(['/usr/bin/rpm', '-qp', '--qf', '%{NAME}|%{VERSION}-%{RELEASE}|%{LICENSE}', str(p)],
                          capture_output=True, text=True).stdout
    name, version, license_text = info.split('|', 2)
    directory = 'p' if name == 'pixman' else 'n' if name.startswith('netpbm') else 'x' if name.startswith('x') else 'm' if name.startswith(('mesa', 'motif')) else 'l'
    rpms.append({'file': str(p), 'sha256': sha(p), 'bytes': p.stat().st_size,
                 'name': name, 'version': version, 'license': license_text,
                 'official_url': 'https://dl.rockylinux.org/pub/rocky/9/AppStream/x86_64/os/Packages/' + directory + '/' + p.name,
                 'signature_verified': True, 'signature_verification_database': str(stage / 'rpms/rpmdb')})

runtime = json.loads((stage / 'runtime-report.json').read_text())
focus = ['afni', '3dAllineate', '3dQwarp', '3dSkullStrip', '3dUnifize', '3dcalc',
         'c3d', 'c3d_affine_tool', 'Xvfb', 'xkbcomp', 'pnmtopng', 'pnmcat', 'pnmcut']
check = '''import json,shutil,subprocess
names=json.loads(__import__('sys').argv[1]); report={}
for name in names:
 p=shutil.which(name)
 r=subprocess.run(['ldd',p],capture_output=True,text=True)
 report[name]={'path':p,'missing': [line.strip() for line in r.stdout.splitlines() if 'not found' in line]}
print(json.dumps(report))'''
r = subprocess.run(['apptainer', 'exec', '--cleanenv', '--no-home', '--bind', '/data:/data',
                    str(image), 'python3', '-c', check, json.dumps(focus)], capture_output=True, text=True)
assert r.returncode == 0, r.stdout + r.stderr
dependency_check = json.loads(r.stdout)
assert not any(v['missing'] for v in dependency_check.values()), dependency_check
(base / 'manifests/AFNI_C3D.dependencies.json').write_text(json.dumps(dependency_check, indent=2))
source_image = Path('/data/xuancheng/agent/PrimateX_1_7.sif')
cache_hash_file = base / 'manifests/existing-images.sha256'
source_image_hash = None
if cache_hash_file.exists() and cache_hash_file.stat().st_mtime >= source_image.stat().st_mtime:
    for line in cache_hash_file.read_text().splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].lstrip('*').strip() == str(source_image):
            source_image_hash = parts[0]
            break
if source_image_hash is None:
    source_image_hash = sha(source_image)
manifest = {
 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status': 'installed_and_validated',
 'image': {'path': str(image), 'sha256': sha(image), 'bytes': image.stat().st_size,
           'architecture': 'x86_64', 'runtime': 'Apptainer 1.4.5', 'gpu_required': False},
 'AFNI': {'version': '26.3.02', 'compile_date': '2026-10-09',
          'official_url': 'https://afni.nimh.nih.gov/pub/dist/tgz/linux_rocky_8.tgz',
          'frozen_archive': str(archive_afni), 'sha256': sha(archive_afni), 'bytes': archive_afni.stat().st_size,
          'license': 'Primarily U.S. Government public domain and CC BY 4.0; bundled components have separate licenses',
          'license_file': str(stage / 'AFNI_LICENSE.txt'),
          'license_official_url': 'https://github.com/afni/afni/blob/master/LICENSE.txt',
          'license_upstream_blob_sha': 'b0a3b74dbd11d9aa7d530522a1cfa76f78fc1656',
          'note': 'Upstream archive URL is rolling; preserved local archive and SHA256 define the installed distribution'},
 'C3D': {'version': '1.4.4', 'release_date': '2025-07-29', 'compile_date': '2025-08-07',
         'source_commit': 'ecdd33ef4fae481cd0bb5161062b54d1907d984b',
         'source_url': 'https://github.com/pyushkevich/c3d/tree/ecdd33ef4fae481cd0bb5161062b54d1907d984b',
         'official_url': 'https://downloads.sourceforge.net/project/c3d/c3d/Experimental/c3d-1.4.4-Linux-gcc64.tar.gz',
         'distribution_channel': 'Official versioned Experimental Linux distribution',
         'frozen_archive': str(archive_c3d), 'sha256': sha(archive_c3d), 'bytes': archive_c3d.stat().st_size,
         'license': 'GPL-3.0', 'license_file': str(base / 'cache/structural_c3d/C3D_COPYING.txt')},
 'os_runtime_snapshot': {'source_image': str(source_image), 'source_image_sha256': source_image_hash,
        'source_image_hash_record': str(cache_hash_file),
        'source_userspace': runtime['source_userspace'], 'dpkg_versions': runtime['dpkg_versions'],
        'glibc': '2.35-0ubuntu3.11', 'libstdcxx': '12.3.0-1ubuntu1~22.04.2',
        'python': 'Ubuntu system Python 3.10.12',
        'scope': runtime['scope'], 'loader_family': 'Consistent Ubuntu glibc/ld-linux family; no RHEL host libc copied',
        'file_inventory': str(stage / 'runtime-report.json'),
        'component_copyrights': '/usr/share/licenses/ubuntu inside the image'},
 'runtime_dependency_rpms': rpms,
 'rocky_verification_key': {'official_url': 'https://dl.rockylinux.org/pub/rocky/RPM-GPG-KEY-Rocky-9',
        'path': str(stage / 'rpms/RPM-GPG-KEY-Rocky-9'), 'sha256': sha(stage / 'rpms/RPM-GPG-KEY-Rocky-9')},
 'validation': {'smoke_summary': str(base / 'tests/afni_c3d/smoke-summary.json'),
        'tests_passed': len(smoke['tests']), 'synthetic_only': True,
        'cross_tool_scale_max_abs_error': smoke['cross_tool_scale_max_abs_error'],
        'qc_pngs': smoke['qc_pngs'], 'selected_elf_dependencies': dependency_check,
        'strict_build_test_log': str(base / 'logs/afni_sif_build_final.log')},
 'recipes': [str(base / 'recipes' / x) for x in ['structural_afni_c3d.def',
        'structural_afni_build_rootfs.py', 'structural_afni_get_qc_rpms.sh', 'structural_afni_smoke.py', 'structural_afni_manifest.py']],
 'limitations': ['Full real MRI @animal_warper processing and species-specific QC have not been run',
       'AFNI R-based statistics are outside this structural image; libR/R packages are not installed',
       'C3D graphical UI is bundled but has not been validated'],
 'preserved': ['Existing SIF files, MRI datasets, FreeSurfer license, GPU driver and system services were not modified']
}
path = base / 'manifests/AFNI_C3D.json'
path.write_text(json.dumps(manifest, indent=2))
print(json.dumps({'manifest': str(path), 'image': manifest['image'], 'tests_passed': len(smoke['tests']),
                  'qc_pngs': smoke['qc_pngs'], 'missing_selected_dependencies': []}, indent=2))
