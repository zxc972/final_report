#!/usr/bin/env python3
"""Numerical and CLI smoke tests using synthetic NIfTI data, never user MRI."""
import gzip
import json
import math
from pathlib import Path
import struct
import subprocess

out = Path('/data/xuancheng/structural_env/tests/afni_c3d')
out.mkdir(parents=True, exist_ok=True)
results = []
def run(args, timeout=90, allowed=(0,)):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=timeout)
    name = str(len(results) + 1) + '_' + Path(args[0]).name.lstrip('@') + '.log'
    (out / name).write_text(p.stdout)
    result = {'command': args, 'exit_code': p.returncode,
              'passed': p.returncode in allowed, 'log': str(out / name)}
    results.append(result)
    if not result['passed']:
        print(p.stdout[-3000:])
        raise RuntimeError('Command failed: ' + repr(args))
    return p.stdout

header = bytearray(352)
struct.pack_into('<i', header, 0, 348)
struct.pack_into('<8h', header, 40, 3, 32, 32, 32, 1, 1, 1, 1)
struct.pack_into('<h', header, 70, 16)
struct.pack_into('<h', header, 72, 32)
struct.pack_into('<8f', header, 76, 1, 1, 1, 1, 1, 1, 1, 1)
struct.pack_into('<f', header, 108, 352)
struct.pack_into('<f', header, 112, 1)
header[123] = 2
struct.pack_into('<h', header, 254, 1)
struct.pack_into('<4f', header, 280, 1, 0, 0, -16)
struct.pack_into('<4f', header, 296, 0, 1, 0, -16)
struct.pack_into('<4f', header, 312, 0, 0, 1, -16)
header[344:348] = b'n+1\0'
values = []
for z in range(32):
    for y in range(32):
        for x in range(32):
            r = ((x - 15.5) / 11)**2 + ((y - 15.5) / 10)**2 + ((z - 15.5) / 9)**2
            values.append(0.0 if r > 1 else 100 + 20 * math.cos(r * 4) + x * 0.25)
phantom = out / 'phantom.nii.gz'
with gzip.open(phantom, 'wb') as f:
    f.write(header)
    f.write(struct.pack('<' + str(len(values)) + 'f', *values))
identity = out / 'identity.1D'
identity.write_text('1 0 0 0 0 1 0 0 0 0 1 0\n')

try:
    run(['afni', '-ver'])
    run(['c3d', '-version'])
    run(['tcsh', '-c', 'echo AFNI_TCSH_OK'])
    run(['@animal_warper', '-help'])
    for command in ['3dAllineate', '3dQwarp', '3dSkullStrip', '3dUnifize']:
        run([command, '-help'])
    dims = run(['3dinfo', '-n4', str(phantom)]).split()
    assert dims[-4:] == ['32', '32', '32', '1'], dims
    scaled = out / 'c3d_scaled.nii.gz'
    run(['c3d', str(phantom), '-scale', '2', '-o', str(scaled)])
    difference = out / 'difference.nii.gz'
    run(['3dcalc', '-overwrite', '-a', str(scaled), '-b', str(phantom),
         '-expr', 'abs(a-2*b)', '-prefix', str(difference)])
    maximum = float(run(['3dBrickStat', '-max', str(difference)]).strip())
    assert maximum == 0.0, maximum
    aligned = out / 'identity_aligned.nii.gz'
    run(['3dAllineate', '-overwrite', '-base', str(phantom), '-input', str(phantom),
         '-1Dmatrix_apply', str(identity), '-final', 'NN', '-prefix', str(aligned)])
    run(['3dinfo', '-n4', str(aligned)])
    run(['c3d_affine_tool', '-sform', str(phantom), '-o', str(out / 'sform.mat')])
    run(['3dQwarp', '-overwrite', '-base', str(phantom), '-source', str(phantom),
         '-prefix', str(out / 'qwarp.nii.gz'), '-maxlev', '0', '-nowarp'], timeout=180)
    run(['3dinfo', '-n4', str(out / 'qwarp.nii.gz')])
    run(['Xvfb', '-help'], allowed=(0,))
    run(['pnmtopng', '-version'])
    run(['@chauffeur_afni', '-ulay', str(phantom), '-prefix', str(out / 'qc'),
         '-montx', '3', '-monty', '3', '-set_xhairs', 'OFF',
         '-save_ftype', 'PNG'], timeout=120)
    pngs = sorted(str(p) for p in out.glob('qc*.png'))
    assert pngs, 'No QC PNG outputs produced'
    summary = {'status': 'passed', 'cross_tool_scale_max_abs_error': maximum,
               'synthetic_dimensions': [32, 32, 32], 'qc_pngs': pngs, 'tests': results}
except Exception as exc:
    summary = {'status': 'failed', 'error': str(exc), 'tests': results}
finally:
    (out / 'smoke-summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
if summary['status'] != 'passed':
    raise SystemExit(1)
