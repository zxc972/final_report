"""Fixed executable discovery and health policies shared by inventory and constraints."""

from __future__ import annotations

import json

# Executed only in the analysis container. No shell or model-supplied argv.
PROBE_SOURCE = r'''
import glob, json, os, re, shutil, subprocess, sys
from pathlib import Path

SOFTWARE_PATTERNS = (
    '/opt/freesurfer*/bin/{name}', '/opt/fsl*/share/fsl/bin/{name}',
    '/opt/fsl*/bin/{name}', '/opt/ants*/bin/{name}',
    '/opt/ants*/{name}', '/opt/workbench/bin_linux64/{name}',
    '/opt/mrtrix*/bin/{name}', '/opt/MATLAB/*/bin/{name}',
    '/usr/local/MATLAB/*/bin/{name}', '/usr/local/MATLAB/bin/{name}',
    '/opt/matlab*/bin/{name}', '/usr/local/bin/{name}',
)

def probe_command(command, lgi_health=False):
    if command.startswith('python:'):
        package = command.split(':', 1)[1]
        if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.]*', package):
            raise ValueError('Registered Python import required')
        paths = [sys.executable]
        argv = [sys.executable, '-I', '-B', '-c', 'import ' + package + '; print(getattr(' + package + ', "__version__", "stdlib"))']
        env = dict(os.environ)
    else:
        found = [shutil.which(command)]
        for pattern in SOFTWARE_PATTERNS:
            found.extend(glob.glob(pattern.format(name=command)))
        paths = sorted(set(p for p in found if p and os.path.isfile(p) and os.access(p, os.X_OK)))
        env = dict(os.environ)
        fs = sorted(glob.glob('/opt/freesurfer*'))
        if fs:
            env['FREESURFER_HOME'] = fs[0]
            env['PATH'] = fs[0] + '/bin:' + env.get('PATH', '')
        argv = [paths[0], '--help'] if paths else []
        if command in ('recon-all', 'wb_command'):
            argv = [paths[0], '-version'] if paths else []
        elif command.startswith(('mris_', 'mri_')):
            argv = [paths[0], '--version'] if paths else []
        elif command == 'matlab':
            argv = [paths[0], '-help'] if paths else []
            if paths and lgi_health:
                fs_matlab = env.get('FREESURFER_HOME', '') + '/matlab'
                check = "addpath(" + repr(fs_matlab) + "); assert(~isempty(ver('images'))); assert(exist('make_outer_surface','file')>0); disp('PRIMATEX_MATLAB_HEALTH_OK')"
                argv = [paths[0], '-batch', check]
    row = {'command': command, 'locations': paths, 'executable_locations': paths,
           'default_path_resolution': shutil.which(command), 'executed': bool(argv),
           'exit_code': None, 'executable': False, 'argv': argv,
           'environment_policy': 'isolated environment; explicit FreeSurfer home for child only'}
    if not argv:
        row['reason'] = 'No executable in registered search locations'
        return row
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL, env=env)
        stdout, stderr = result.stdout[:1500], result.stderr[:1500]
        valid_version_exit = (command == 'mris_info' and result.returncode == 1
                              and not stderr.strip()
                              and bool(re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?', stdout.strip())
                                       or re.search(r'mris_info.*\d+\.\d+', stdout, re.I)))
        row.update(exit_code=result.returncode, stdout=stdout, stderr=stderr,
                   executable=result.returncode == 0 or valid_version_exit,
                   accepted_nonzero_version_exit=valid_version_exit)
        if command.startswith('python:') and result.returncode == 0:
            row['version'] = stdout.strip()[:100]
        if command == 'matlab' and lgi_health:
            row['executable'] = result.returncode == 0 and 'PRIMATEX_MATLAB_HEALTH_OK' in result.stdout
    except Exception as exc:
        row['error'] = type(exc).__name__ + ': ' + str(exc)[:500]
    return row
'''


def software_probe_source(commands: list[str], lgi_health: bool = False) -> str:
    return PROBE_SOURCE + (
        "\nrows = [probe_command(c, " + repr(lgi_health) + ") for c in "
        + repr(commands) + "]\n"
        + "print('PRIMATEX_CONSTRAINT_PROBE=' + json.dumps({'commands': rows}))\n"
    )
