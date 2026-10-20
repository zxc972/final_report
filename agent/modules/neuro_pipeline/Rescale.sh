#!/usr/bin/env bash
# Copyright (C) 2026 Wang Zheng Lab, Peking University
#
# This file is part of PrimateX.
#
# PrimateX is free software: you can redistribute it and/or modify it under the
# terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# PrimateX is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# If you use PrimateX in academic work, please cite:
# Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.
# Multi-agentic routing with PrimateX: standardized structural MRI analysis
# for non-human primates and humans.
#
# * Equal contribution.
# Correspondence (#): Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang
# (zheng.wang@pku.edu.cn).
#
# See CITATION.cff for full citation details.

# -----------------------------------------------------------------------------
#  Rescale.sh — Convert "fake‑1 mm" FreeSurfer outputs back to native resolution
# -----------------------------------------------------------------------------
#  Motivation : Preprocess_3_1 generates intermediate surfaces/volumes in a
#               conformed 1 mm grid.  For downstream analysis we need the
#               species-specific native resolution (macaque 0.5 mm,
#               chimpanzee 0.8 mm, marmoset 0.2 mm). This script rescales MRI
#               volumes and surface meshes, preserving transforms and labels.
#
#  Steps
#  ─────
#     1. Rename   <SUB>/<SUB>  →  <SUB>/<SUB>_1mm   (backup)
#     2. Create new subject folder hierarchy
#     3. For each key MRI volume (rawavg, orig, brain.finalsurfs …)
#          • convert mgz → nifti
#          • header‑scale to the species-specific voxel size (Python helper)
#          • back to mgz in new folder
#     4. Surfaces (white / smoothwm / pial): mri_surf2surf with rescale matrix
#     5. Copy spheres, curv, sulc, labels
#     6. Re‑compute thickness & anatomical stats
#
#  Usage :  ./Rescale.sh -id <SUB_ID> -out_path <OUT_PATH> [-species|--species <SPECIES>]
#           # SUBJECTS_DIR (OUT_PATH/SUB_ID) must point to 1‑mm pipeline folder
#           # species is case-insensitive; cynomolgus/rhesus map to Macaque
#
#  Example:
#     singularity exec -B /data:/data neurotools.sif  \
#         ./Rescale.sh -id KM001 -out_path /data/KM001 -species macaque
# -----------------------------------------------------------------------------
#  Author  :  Yichun Huang  <ychunhuang@foxmail.com>
#  Updated :  2025‑06‑10
# -----------------------------------------------------------------------------

set -euo pipefail

# ───────────────────────── helper functions ──────────────────────────
usage() { grep -E "^#  " "$0" | cut -c4- ; exit 0; }
log()   { printf '\e[1;36m[INFO]  %s\e[0m\n'  "$*"; }
err()   { printf '\e[1;31m[ERROR] %s\e[0m\n' "$*" >&2; exit 1; }

# ───────────────────────── argument parsing ─────────────────────────
[[ $# -eq 0 ]] && { err "No arguments provided"; }

# Default values
SPECIES=Macaque          # macaque 0.5mm, chimpanzee 0.8mm, marmoset 0.2mm

while [[ $# -gt 0 ]]; do
    case "$1" in
		-id|--subject)  SUB_ID="${2:?missing subject ID}" ; shift 2 ;;
		-out_path)      OUT_DIR="${2:?missing out dir}"   ; shift 2 ;;
        -species|--species)
			SPECIES="${2:?missing species}" ; shift 2 ;;
		-h|--help)      usage ; exit 0                     ;;
		*)              err "Unknown option: $1"           ;;
	esac
done

# Normalize species input (trim + case-insensitive) and support aliases.
_species_raw="$SPECIES"
_species_lc="$(printf '%s' "${SPECIES:-}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | tr '[:upper:]' '[:lower:]')"
case "$_species_lc" in
	macaque|cynomolgus|rhesus) SPECIES="Macaque" ;;
	chimpanzee)               SPECIES="Chimpanzee" ;;
	marmoset)                 SPECIES="Marmoset" ;;
	*)
		err "Unknown species: ${_species_raw}. Use macaque|cynomolgus|rhesus|chimpanzee|marmoset (case-insensitive)."
		;;
esac

# Set voxel size based on species
case "$SPECIES" in
    Macaque)     VOXEL_SIZE=0.5 ;;
    Chimpanzee)  VOXEL_SIZE=0.8 ;;
    Marmoset)    VOXEL_SIZE=0.2 ;;
    *)           err "Unknown species: $SPECIES" ;;
esac
log "Species: $SPECIES, Voxel size: ${VOXEL_SIZE}mm"
VOXEL_SIZE=$(printf "%smm" "${VOXEL_SIZE//.}") # -> 05mm, 08mm, 02mm

[[ -z ${SUB_ID:-} ]] && err "Subject ID (-id) is required"
[[ -z ${OUT_DIR:-} ]] && err "Output directory (-out_path) is required"

# ─────────────────────── env / path setup ────────────────────────────
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
TEMPLATE_DIR="$SCRIPT_DIR/template/"
PY_UTIL="${SCRIPT_DIR}/pyscript/Resample_to_specific.py"

# Rescale matrix for different species
RESCALE_MAT="$TEMPLATE_DIR/fs_xfms/${SPECIES}_rescale.dat"

log "Rescaling subject $SUB_ID in $OUT_DIR"
log "Rescale matrix (.dat) = $RESCALE_MAT"

# =====================================================================
# STEP 0  | Folder Scaffolding
# =====================================================================
log "[0] Move and Create new subject folder hierarchy"
mv "$OUT_DIR/$SUB_ID" "$OUT_DIR/${SUB_ID}_1mm"

ORIG_SUB_DIR="$OUT_DIR/${SUB_ID}_1mm"  # backup of 1 mm outputs
NEW_SUB_DIR="$OUT_DIR/$SUB_ID"         # final 0.5 mm subject dir

mkdir -p "$NEW_SUB_DIR"/mri/transforms "$NEW_SUB_DIR"/{surf,label,stats}

# =====================================================================
# STEP 1  | Volume Rescaling
# =====================================================================
log "[1] Rescale MRI volumes to ${VOXEL_SIZE}"
MRI_LIST=(rawavg orig brain.finalsurfs brainmask wm aseg.presurf)
for vol in "${MRI_LIST[@]}"; do
    SRC_MGZ="$ORIG_SUB_DIR/mri/${vol}.mgz"
    [[ -f $SRC_MGZ ]] || err "$SRC_MGZ missing"
    tmp_nii="$ORIG_SUB_DIR/mri/${vol}.nii.gz"
    mri_convert "$SRC_MGZ" "$tmp_nii"
    python3 "$PY_UTIL" "$ORIG_SUB_DIR/mri" "${vol}.nii.gz" "${VOXEL_SIZE}" "$vol"   # → ${vol}_${VOXEL_SIZE}.nii.gz
    mv "$ORIG_SUB_DIR/mri/${vol}_${VOXEL_SIZE}.nii.gz" "$NEW_SUB_DIR/mri/${vol}.nii.gz"
    mri_convert "$NEW_SUB_DIR/mri/${vol}.nii.gz" "$NEW_SUB_DIR/mri/${vol}.mgz"
    rm -f "$tmp_nii"
    log "   • $vol done"
done

# copy transforms (needed for thickness/stats)
cp -r "$ORIG_SUB_DIR/mri/transforms"/* "$NEW_SUB_DIR/mri/transforms/"

# =====================================================================
# STEP 2  | Surface Rescaling
# =====================================================================
log "[2] Rescale key surfaces (white / smoothwm / pial)"
export SUBJECTS_DIR="$OUT_DIR"   # so mri_surf2surf can find subjects
for surf in white smoothwm pial; do
    for hemi in lh rh; do
        # mri_surf2surf --s "${SUB_ID}_1mm" --hemi "$hemi" \
        #             --sval-xyz "$surf" \
        #             --reg-inv "$RESCALE_MAT" \
        #             --tval-xyz "$NEW_SUB_DIR/mri/brain.finalsurfs.mgz" \
        #             --tval "${surf}_temp"
        mri_surf2surf --s "${SUB_ID}_1mm" --hemi "$hemi" \
            --sval-xyz "$surf" \
            --reg-inv "$RESCALE_MAT" "$NEW_SUB_DIR/mri/brain.finalsurfs.mgz" \
            --tval-xyz "$OUT_DIR/T1.nii.gz" \
            --tval "${surf}_temp"
        mv "$ORIG_SUB_DIR/surf/${hemi}.${surf}_temp" "$NEW_SUB_DIR/surf/${hemi}.${surf}"
    done
    log "   • $surf surfaces done"
done

# =====================================================================
# STEP 3  | Copy Spheres, Curvature, Labels
# =====================================================================
log "[3] Copy spheres, curvature & label files"
cp "$ORIG_SUB_DIR"/surf/{lh,rh}.sphere*    "$NEW_SUB_DIR/surf/"
cp "$ORIG_SUB_DIR"/surf/{lh,rh}.{curv,sulc} "$NEW_SUB_DIR/surf/"
cp "$ORIG_SUB_DIR"/label/*                 "$NEW_SUB_DIR/label/"

# =====================================================================
# STEP 4  | Recompute Thickness & Stats
# =====================================================================
log "[4] Re‑compute thickness & anatomical stats"
for hemi in lh rh; do
    mris_thickness "$SUB_ID" "$hemi" "${hemi}.thickness" >/dev/null 2>&1
    for annot in aparc aparc.a2009s; do
        mris_anatomical_stats -a "$NEW_SUB_DIR/label/${hemi}.${annot}.annot" \
                                -f "$NEW_SUB_DIR/stats/${hemi}.${annot}.stats" \
                                -b "$SUB_ID" "$hemi" >/dev/null 2>&1
    done
    log "   • $hemi thickness & stats done"
done

log "Rescale pipeline DONE ✅"
