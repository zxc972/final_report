#!/bin/bash
set -euo pipefail
root=/data/xuancheng/structural_env
target="$root/templates/human/FSL_6.0.7.8_standard"
mkdir -p "$target"
apptainer exec --cleanenv --no-home /data/xuancheng/agent/PrimateX_1_7.sif tar -C /opt/fsl-6.0.7.8/data/standard -cf - . | tar --no-same-owner -C "$target" -xf -
average=/data/xuancheng/featurize_20261011/data/fastsurfer_public_20261010/native12/verified_fs16/opt/freesurfer/subjects/fsaverage
if [ -d "$average" ] && [ ! -e "$root/templates/human/fsaverage-existing" ]; then ln -s "$average" "$root/templates/human/fsaverage-existing"; fi
find "$target" -type f -print0 | sort -z | xargs -0 sha256sum > "$root/manifests/human-fsl-templates.sha256"
cat > "$root/manifests/HumanTemplates.json" <<'JSON'
{
  "status": "available",
  "downloaded_again": false,
  "FSL_standard": {
    "source_image": "/data/xuancheng/agent/PrimateX_1_7.sif",
    "source_inside_container": "/opt/fsl-6.0.7.8/data/standard",
    "copied_to": "/data/xuancheng/structural_env/templates/human/FSL_6.0.7.8_standard",
    "official_license": "https://fsl.fmrib.ox.ac.uk/fsl/docs/license.html"
  },
  "fsaverage": {
    "mode": "reference existing migrated template",
    "path": "/data/xuancheng/structural_env/templates/human/fsaverage-existing",
    "source": "/data/xuancheng/featurize_20261011/data/fastsurfer_public_20261010/native12/verified_fs16/opt/freesurfer/subjects/fsaverage"
  }
}
JSON
echo HUMAN_TEMPLATES_AVAILABLE
