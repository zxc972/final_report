#!/bin/bash
set -euo pipefail
root=/data/xuancheng/structural_env
image="$root/images/primatex-legacy.sif"
target="$root/runtime/python-analysis-restored"
if [ -e "$target" ]; then echo "Refusing to overwrite $target"; exit 1; fi
apptainer exec --cleanenv --no-home --bind /data:/data "$image" /bin/bash --noprofile --norc -s <<'INNER'
set -euo pipefail
unset PYTHONPATH PYTHONHOME
root=/data/xuancheng/structural_env
target="$root/runtime/python-analysis-restored"
python -m venv --copies "$target"
"$target/bin/python" -m pip install --no-index --find-links "$root/cache/python-wheels" -r "$root/recipes/python-analysis.lock.txt"
"$target/bin/python" -m pip check
INNER
