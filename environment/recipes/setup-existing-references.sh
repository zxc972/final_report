#!/bin/bash
set -euo pipefail
root=/data/xuancheng/structural_env
link_reference() {
  source=$1; destination=$2
  if [ -L "$destination" ]; then
    [ "$(readlink "$destination")" = "$source" ] || { echo "Conflicting reference: $destination"; exit 1; }
  elif [ -e "$destination" ]; then
    echo "Refusing to replace existing path: $destination"; exit 1
  else ln -s "$source" "$destination"; fi
}
link_reference /data/xuancheng/agent/PrimateX_1_7.sif "$root/images/primatex-legacy.sif"
link_reference /data/xuancheng/human_fastsurfer/containers/fastsurfer-cu118-v2.5.4.sif "$root/images/fastsurfer-cu118.sif"
link_reference /data/PrimateX-main_new/modules/primx_seg/models "$root/models/primx-existing"
cat > "$root/manifests/existing-references.json" <<'JSON'
{
  "mode": "references to existing files, original contents unchanged",
  "images": {
    "primatex-legacy.sif": "/data/xuancheng/agent/PrimateX_1_7.sif",
    "fastsurfer-cu118.sif": "/data/xuancheng/human_fastsurfer/containers/fastsurfer-cu118-v2.5.4.sif"
  },
  "models": "/data/PrimateX-main_new/modules/primx_seg/models",
  "license_runtime_only": "/data/xuancheng/license.txt",
  "known_versions": {
    "FSL": "6.0.7.8", "ANTs": "2.4.3", "FreeSurfer": "7.2.0",
    "Workbench": "2.1.0", "MRtrix3": "3.0.2", "dcm2niix": "1.0.20250505",
    "legacy_python": "3.10.19", "legacy_torch": "2.0.1", "legacy_monai": "1.3.0"
  }
}
JSON
sha256sum /data/xuancheng/agent/PrimateX_1_7.sif /data/xuancheng/human_fastsurfer/containers/fastsurfer-cu118-v2.5.4.sif > "$root/manifests/existing-images.sha256"
du -sh "$root"
echo REFERENCE_SETUP_COMPLETE
