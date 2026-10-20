#!/bin/bash
set -euo pipefail
umask 022
root=/data/xuancheng/structural_env
image=/data/xuancheng/agent/PrimateX_1_7.sif
envdir="$root/runtime/python-analysis"
wheelhouse="$root/cache/python-wheels"
mkdir -p "$wheelhouse" "$root/recipes" "$root/manifests" "$root/logs"
if [ -e "$envdir" ] && [ ! -f "$envdir/pyvenv.cfg" ]; then echo 'Unexpected existing environment path'; exit 1; fi
printf '%s\n' nilearn nipype pybids numpy scipy pandas matplotlib scikit-learn nibabel SimpleITK > "$root/recipes/python-analysis.in"
apptainer exec --cleanenv --no-home --bind /data:/data "$image" /bin/bash --noprofile --norc -s <<'INNER'
set -euo pipefail
unset PYTHONPATH PYTHONHOME
root=/data/xuancheng/structural_env
envdir="$root/runtime/python-analysis"
export PIP_CACHE_DIR="$root/cache/pip"
export MPLCONFIGDIR="$root/cache/matplotlib"
export PIP_DISABLE_PIP_VERSION_CHECK=1
if [ ! -f "$envdir/pyvenv.cfg" ]; then python -m venv --copies "$envdir"; fi
"$envdir/bin/python" -m pip wheel --wheel-dir "$root/cache/python-wheels" -r "$root/recipes/python-analysis.in" --timeout 30 --retries 3
"$envdir/bin/python" -m pip install --no-index --find-links "$root/cache/python-wheels" --report "$root/manifests/python-install-report.json" -r "$root/recipes/python-analysis.in"
"$envdir/bin/python" -m pip check
"$envdir/bin/python" -m pip freeze > "$root/recipes/python-analysis.lock.txt"
"$envdir/bin/python" -m pip list --format=json > "$root/manifests/python-packages.json"
"$envdir/bin/python" - <<'PY'
import sys, json, importlib.metadata as m
from pathlib import Path
import numpy, scipy, pandas, matplotlib, sklearn, nibabel, SimpleITK, nilearn, nipype, bids
root = Path('/data/xuancheng/structural_env')
names=['nilearn','nipype','pybids','numpy','scipy','pandas','matplotlib','scikit-learn','nibabel','SimpleITK']
manifest={'status':'installed','mode':'isolated venv inside existing PrimateX SIF','python':sys.version,'base_image':'/data/xuancheng/agent/PrimateX_1_7.sif','environment':str(root/'runtime/python-analysis'),'packages':{x:m.version(x) for x in names},'source':'https://pypi.org/simple/','torch_monai_changed':False}
(root/'manifests/PythonAnalysis.json').write_text(json.dumps(manifest,indent=2)+'\n')
licenses=root/'licenses/python-distributions'; licenses.mkdir(exist_ok=True)
for dist in m.distributions():
    folder=licenses/(dist.metadata['Name']+'-'+dist.version); folder.mkdir(exist_ok=True)
    (folder/'METADATA.txt').write_text(dist.read_text('METADATA') or '',encoding='utf-8')
    for file in dist.files or []:
        name=str(file).lower()
        if '.dist-info/' in name and ('license' in name or 'copying' in name or 'notice' in name):
            source=Path(dist.locate_file(file))
            if source.is_file():
                destination=folder/str(file).split('.dist-info/',1)[1]
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(source.read_bytes())
print(json.dumps(manifest,indent=2))
PY
INNER
find "$wheelhouse" -maxdepth 1 -type f -name '*.whl' -print0 | sort -z | xargs -0 sha256sum > "$root/manifests/python-wheels.sha256"
echo 'PYTHON_INSTALL_COMPLETE'
