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
#  Preprocess_3_1.sh — FreeSurfer autorecon‑1 + DL‑guided mask & WM fixes
# -----------------------------------------------------------------------------
#  OVERVIEW
#  ---------------------------------------------------------------------------
#   0.  Truncate extreme intensities  (ANTs ImageMath)  ➜ T1_truncate
#   1.  Resample   T1_truncate → 1 mm                (Python helper)
#   2.  FreeSurfer autorecon‑1 (no skull‑strip)
#   3.  Replace FS brainmask with DL mask (registered)
#   4.  Lightweight Talairach alignment and GCA intensity normalization
#   5.  Macaque/Marmoset: ANTs atlas → subject → FreeSurfer space
#   6.  Optional hybrid aseg: warped atlas anatomy + DL cortical WM
#   7.  Generate brain.finalsurfs and wm.mgz from the final aseg
#
#  REQUIREMENTS
#    • FreeSurfer 7.x       (recon-all, mri_* family)
#    • FSL 6.x              (flirt, fslmaths)
#    • ANTs 2.3+            (ImageMath, antsRegistrationSyN.sh)
#    • Python3 + nibabel    (Resample_to_specific.py)
#
#  USAGE
#      ./Preprocess_3_1.sh  -id <SUB_ID>  -out_path <out_path> [-species <SPECIES>]
#                           [-hybrid-aseg|-no-hybrid-aseg] [-threads <N>]
#  Required :
#     -id            subject ID (folder name under <out_path>)
#     -out_path      working / output directory
#  Optional :
#     -species       case-insensitive:
#                    • Macaque/Cynomolgus/Rhesus  -> 0.5mm (share same pipeline logic)
#                    • Chimpanzee                -> 0.8mm
#                    • Marmoset                  -> 0.2mm
#                    (Default: Macaque)
#     -hybrid-aseg   For atlas-based species, replace atlas cortical WM labels
#                    with the registered DL WM mask and rebuild cortical GM.
#                    Enabled by default. This can change the white surface.
#     -no-hybrid-aseg
#                    Keep the pure warped atlas as aseg.presurf for A/B testing.
#     -threads N      Overall thread count for supported FreeSurfer and ANTs
#                    commands. Must be a positive integer. (Default: 1)
#
#  EXAMPLE (inside singularity / conda env with FS + FSL + ANTs)
#      singularity exec -B /data:/data neurotools.sif  \
#         ./Preprocess_3_1.sh -id KM001 -out_path /data/KM001 -species macaque
# -----------------------------------------------------------------------------
#  CHANGELOG (excerpt)
#  2026-07-23  Atlas-first aseg flow + optional DL-WM hybrid aseg (Codex)
#  2025‑06‑10  Refactor: full comments, logging, path quotes (Y.C.H.)
#  2024‑10‑10  Formatting tweaks
#  2023‑02‑21  Added -notal-check to autorecon1
# -----------------------------------------------------------------------------

set -euo pipefail

# ─────────────────────── helper functions ────────────────────────────
usage()  { grep -E "^#  " "$0" | cut -c4- ; }
log()    { printf '\e[1;36m[INFO]  %s\e[0m\n'  "$*"; }
warn()   { printf '\e[1;33m[WARN]  %s\e[0m\n'  "$*"; }
err()    { printf '\e[1;31m[ERROR] %s\e[0m\n' "$*" >&2; exit 1; }

# ─────────────────────── argument parsing ────────────────────────────
[[ $# -eq 0 ]] && { err "No arguments provided"; }

# Default values
SPECIES=Macaque          # macaque 0.5mm, chimpanzee 0.8mm, marmoset 0.2mm
USE_HYBRID_ASEG=1        # explicit A/B switch; hybrid can change white geometry
THREADS=1                # conservative default for reproducibility

while [[ $# -gt 0 ]]; do
    case "$1" in
		-id|--subject)  SUB_ID="${2:?missing subject ID}" ; shift 2 ;;
		-out_path)      OUT_DIR="${2:?missing out dir}"   ; shift 2 ;;
        -species)       SPECIES="${2}" ; shift 2 ;;
		-hybrid-aseg)    USE_HYBRID_ASEG=1 ; shift ;;
		-no-hybrid-aseg) USE_HYBRID_ASEG=0 ; shift ;;
		-threads|--threads)
			THREADS="${2:?missing thread count}" ; shift 2
			;;
		-h|--help)      usage ; exit 0                     ;;
		*)              err "Unknown option: $1"           ;;
	esac
done

[[ $THREADS =~ ^[1-9][0-9]*$ ]] || err "-threads must be a positive integer"
log "Thread count: $THREADS"

# Normalize species (case-insensitive) + aliases
# Accept: macaque/cynomolgus/rhesus, chimpanzee, marmoset (any case)
_species_lc="$(printf '%s' "${SPECIES:-}" | tr '[:upper:]' '[:lower:]')"
case "$_species_lc" in
	macaque|cynomolgus|rhesus) SPECIES="Macaque" ;;
	chimpanzee)               SPECIES="Chimpanzee" ;;
	marmoset)                 SPECIES="Marmoset" ;;
	*) err "Unknown species: $SPECIES (supported: Macaque|Cynomolgus|Rhesus|Chimpanzee|Marmoset; case-insensitive)" ;;
esac

# Set voxel size based on species (standardized above)
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

JOB_DIR="$OUT_DIR"
[[ -d $JOB_DIR ]] || err "Directory $JOB_DIR not found"

# ─────────────────────── env / path setup ────────────────────────────
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
TEMPLATE_DIR="$SCRIPT_DIR/template/$SPECIES"
PY_UTIL="${SCRIPT_DIR}/pyscript/Resample_to_specific.py"

T1_RAW="$JOB_DIR/T1.nii.gz"
MASK_DL="$JOB_DIR/brain_mask.nii.gz"
[[ -f $T1_RAW && -f $MASK_DL ]] || err "T1.nii.gz or brain_mask.nii.gz missing in $JOB_DIR"

export SUBJECTS_DIR="$JOB_DIR"   # FreeSurfer expects this
FS_SUB_DIR="$SUBJECTS_DIR/$SUB_ID"
FS_MRI_DIR="$FS_SUB_DIR/mri"
FS_FIX_BM="$FS_MRI_DIR/fix_bm"
FS_FIX_WM="$FS_MRI_DIR/fix_wm"

log "SUBJECTS_DIR = $SUBJECTS_DIR"

cd "$JOB_DIR"/tmp || err "Failed to cd to $JOB_DIR/tmp"

# =====================================================================
# STEP 0  | Intensity truncation + 1 mm resample
# =====================================================================
log "[0] Truncate intensities + resample to 1 mm"
ImageMath 3 "$JOB_DIR/T1_truncate.nii.gz" TruncateImageIntensity "$T1_RAW"
python3 "$PY_UTIL" "$JOB_DIR"  T1_truncate.nii.gz  1mm  T1   # ➜ T1_1mm.nii.gz

# =====================================================================
# STEP 1  | FreeSurfer autorecon‑1 (no skull‑strip)
# =====================================================================
log "[1] FreeSurfer autorecon‑1 (noskullstrip)"
recon-all -i "$JOB_DIR/T1_1mm.nii.gz" -s "$SUB_ID" \
        -autorecon1 -noskullstrip -notal-check -openmp "$THREADS"

# =====================================================================
# STEP 2  | Replace FS brainmask with DL brainmask
# =====================================================================
log "[2] Replace FS brainmask with DL mask"

# Create directories for fix_bm and fix_wm after freesurfer autorecon1
mkdir -p "$FS_FIX_BM" "$FS_FIX_WM"

# 2.1 Convert FS T1 to NIfTI (0.5 mm)
mri_convert "$FS_MRI_DIR/T1.mgz" "$FS_FIX_BM/T1.nii.gz" # (freesurfer generated) (1x1x1)
python3 "$PY_UTIL" "$FS_FIX_BM" "T1.nii.gz" "${VOXEL_SIZE}" T1  # ➜ T1_${VOXEL_SIZE}.nii.gz (0.5x0.5x0.5)
mv "$FS_FIX_BM/T1_${VOXEL_SIZE}.nii.gz" "$FS_FIX_BM/FS_T1_${VOXEL_SIZE}.nii.gz" # rename for clarity ➜ FS_T1_${VOXEL_SIZE}.nii.gz

# 2.2 Register DL T1_truncate to FS 0.5 mm space
flirt -ref "$FS_FIX_BM/FS_T1_${VOXEL_SIZE}.nii.gz" \
    -in  "$JOB_DIR/T1_truncate.nii.gz" \
	-out "$FS_FIX_BM/T1_TO_FS.nii.gz" \
    -omat "$FS_FIX_BM/T1_TO_FS.mat" -dof 12 \
    -searchrx -180 180 -searchry -180 180 -searchrz -180 180

flirt -ref "$FS_FIX_BM/T1_TO_FS.nii.gz" \
    -in  "$MASK_DL" -applyxfm -init "$FS_FIX_BM/T1_TO_FS.mat" \
    -out "$FS_FIX_BM/brainmask_TO_FS.nii.gz" -interp nearestneighbour

# 2.3 Binarise + upsample to 1 mm
python3 "$PY_UTIL" "$FS_FIX_BM" brainmask_TO_FS.nii.gz 1mm brainmask_TO_FS
fslmaths "$FS_FIX_BM/brainmask_TO_FS_1mm.nii.gz" -bin "$FS_FIX_BM/brainmask_TO_FS_1mm.nii.gz"

# 2.4 Mask FS T1 & convert to .mgz brain_mask.auto
fslmaths "$FS_FIX_BM/T1.nii.gz" -mas "$FS_FIX_BM/brainmask_TO_FS_1mm.nii.gz" \
        "$FS_FIX_BM/brain_replaced.nii.gz" # 1x1x1

mri_mask "$FS_FIX_BM/brain_replaced.nii.gz" "$FS_FIX_BM/T1.nii.gz" \
        "$FS_MRI_DIR/brain_mask.auto.mgz"

# Update xform (talairach.xfm will exist after autorecon1)
mri_add_xform_to_header -c "$FS_SUB_DIR/transforms/talairach.xfm" \
        "$FS_MRI_DIR/brain_mask.auto.mgz" "$FS_MRI_DIR/brain_mask.auto.mgz"
cp "$FS_MRI_DIR/brain_mask.auto.mgz" "$FS_MRI_DIR/brainmask.mgz"

# =====================================================================
# STEP 3 | Lightweight Talairach alignment and GCA normalization
# =====================================================================
log "[3] $SPECIES Talairach alignment and intensity normalization"
GCA="$TEMPLATE_DIR/RB_all_2008-03-26.gca"
if [[ $SPECIES == "Marmoset" ]]; then
	GCA="$TEMPLATE_DIR/RB_all_2018-01-26.gca"
fi

# talairach.lta remains required by mri_fill. mri_ca_normalize provides the
# GCA-normalized T1 used by the later surface placement steps.
mri_em_register -threads "$THREADS" -uns 3 -mask "$FS_MRI_DIR/brainmask.mgz" \
	"$FS_MRI_DIR/nu.mgz" "$GCA" "$FS_MRI_DIR/transforms/talairach.lta"
mri_ca_normalize -mask "$FS_MRI_DIR/brainmask.mgz" \
	"$FS_MRI_DIR/nu.mgz" "$GCA" "$FS_MRI_DIR/transforms/talairach.lta" "$FS_MRI_DIR/norm.mgz"

mkdir -p "$JOB_DIR/templates_reg"
# Keep the atlas-registration target separate from ACPC_Alignment.sh's
# brain.nii.gz. Chimpanzee has no warped label atlas and retains that original
# T1-based image for its established DL-WM registration.
ATLAS_REG_BRAIN="$FS_FIX_WM/T1_truncate_brain.native.nii.gz"
fslmaths "$JOB_DIR/T1_truncate.nii.gz" -mul "$MASK_DL" "$ATLAS_REG_BRAIN"
DL_REG_BRAIN="$ATLAS_REG_BRAIN"
if [[ $SPECIES == "Chimpanzee" ]]; then
	DL_REG_BRAIN="$JOB_DIR/brain.nii.gz"
fi

DL_WM_AVAILABLE=0
CHIMP_CLAUSTRUM_AVAILABLE=0

prepare_dl_wm_in_fs_space() {
	[[ -f $JOB_DIR/wm.nii.gz ]] || return 1

	log "Register DL WM prediction → FreeSurfer working space"
	cp "$JOB_DIR/wm.nii.gz" "$FS_FIX_WM/wm_orig.nii.gz"
	cp "$DL_REG_BRAIN" "$FS_FIX_WM/brain_orig.nii.gz"
	cp "$FS_FIX_BM/brain_replaced.nii.gz" "$FS_FIX_WM/brain_replaced.nii.gz"
	python3 "$PY_UTIL" "$FS_FIX_WM" brain_replaced.nii.gz "$VOXEL_SIZE" brain_replaced

	flirt -ref "$FS_FIX_WM/brain_replaced_${VOXEL_SIZE}.nii.gz" \
		-in "$FS_FIX_WM/brain_orig.nii.gz" \
		-omat "$FS_FIX_WM/brain_for_fix_wm.mat" -dof 12 \
		-searchrx -180 180 -searchry -180 180 -searchrz -180 180
	flirt -ref "$FS_FIX_WM/brain_replaced_${VOXEL_SIZE}.nii.gz" \
		-in "$FS_FIX_WM/wm_orig.nii.gz" \
		-applyxfm -init "$FS_FIX_WM/brain_for_fix_wm.mat" \
		-out "$FS_FIX_WM/wm_replaced_${VOXEL_SIZE}.nii.gz" \
		-interp nearestneighbour
	python3 "$PY_UTIL" "$FS_FIX_WM" "wm_replaced_${VOXEL_SIZE}.nii.gz" 1mm wm_replaced

	fslmaths "$FS_FIX_WM/wm_replaced_1mm.nii.gz" -bin -mul 111 "$FS_FIX_WM/wm_dl_111.nii.gz"
	# Preserve 111 as an ordinary automatic WM value. Without -ns 1,
	# mri_convert rescales the float NIfTI range and turns 111 into the
	# reserved manual-edit value 255.
	mri_convert -ns 1 -odt uchar "$FS_FIX_WM/wm_dl_111.nii.gz" \
		"$FS_FIX_WM/wm_dl_111.mgz"
	DL_WM_AVAILABLE=1
}

warp_species_atlas_to_fs() {
	local atlas_prefix="$JOB_DIR/templates_reg/${SPECIES}_atlas_to_T1_"

	log "Register $SPECIES template → subject and warp FreeSurfer labels"
	antsRegistrationSyN.sh -d 3 -n "$THREADS" \
		-f "$ATLAS_REG_BRAIN" -m "$NMT_REF" \
		-o "$atlas_prefix"
	ConvertTransformFile 3 "${atlas_prefix}0GenericAffine.mat" \
		"${atlas_prefix}0GenericAffine.txt"

	REF_IMG="$ATLAS_REG_BRAIN"
	W1="${atlas_prefix}1Warp.nii.gz"
	AFF_TXT="${atlas_prefix}0GenericAffine.txt"

	WarpImageMultiTransform 3 "$FS_ATLAS" "$FS_FIX_WM/fs_atlas.nii.gz" \
		-R "$REF_IMG" "$W1" "$AFF_TXT" --use-NN

	fslmaths "$FS_FIX_BM/brainmask_TO_FS.nii.gz" \
		-mul "$FS_FIX_BM/FS_T1_${VOXEL_SIZE}.nii.gz" "$FS_FIX_BM/FS_brain.nii.gz"
	flirt -ref "$FS_FIX_BM/FS_brain.nii.gz" -in "$REF_IMG" \
		-omat "$FS_FIX_WM/brain_for_fix_fs.mat" -dof 12 \
		-searchrx -180 180 -searchry -180 180 -searchrz -180 180
	flirt -ref "$FS_FIX_BM/FS_brain.nii.gz" -in "$FS_FIX_WM/fs_atlas.nii.gz" \
		-applyxfm -init "$FS_FIX_WM/brain_for_fix_fs.mat" \
		-out "$FS_FIX_WM/brain_for_fix_fs_space.nii.gz" \
		-interp nearestneighbour
	python3 "$PY_UTIL" "$FS_FIX_WM" brain_for_fix_fs_space.nii.gz 1mm brain_TO_FS_fix_wm

	# This is a discrete label map: never rescale label values while
	# converting the float NIfTI produced by the registration utilities.
	mri_convert -ns 1 -odt uchar "$FS_FIX_WM/brain_TO_FS_fix_wm_1mm.nii.gz" \
		"$FS_MRI_DIR/aseg.presurf.atlas.mgz"
	cp "$FS_MRI_DIR/aseg.presurf.atlas.mgz" "$FS_MRI_DIR/aseg.presurf.mgz"
}

build_hybrid_aseg() {
	local hybrid_dir="$FS_FIX_WM/hybrid_aseg"
	mkdir -p "$hybrid_dir"

	# ==================================================================
	# HYBRID ASEG EXPERIMENTAL STEP
	#
	# This block CAN CHANGE THE WHITE SURFACE. It makes the volumetric
	# aseg consistent with the DL WM that initializes wm.mgz:
	#   * warped atlas retains subcortical/ventricle/CC anatomy;
	#   * DL WM replaces atlas cortical WM labels 2/41;
	#   * the remaining atlas cortical envelope becomes GM labels 3/42.
	#
	# Use -no-hybrid-aseg to bypass this entire block and test the pure
	# warped atlas. Both aseg.presurf.atlas.mgz and
	# aseg.presurf.hybrid.mgz are retained for direct QC comparison.
	# ==================================================================
	log "[HYBRID ASEG] Merge warped atlas anatomy with DL cortical WM"

	mri_convert "$FS_MRI_DIR/aseg.presurf.atlas.mgz" "$hybrid_dir/atlas.nii.gz"

	# Cortical envelopes also serve as left/right distance seeds.
	fslmaths "$hybrid_dir/atlas.nii.gz" -thr 2 -uthr 3 -bin "$hybrid_dir/lh.cortex"
	fslmaths "$hybrid_dir/atlas.nii.gz" -thr 41 -uthr 42 -bin "$hybrid_dir/rh.cortex"
	fslmaths "$hybrid_dir/lh.cortex" -add "$hybrid_dir/rh.cortex" -bin \
		"$hybrid_dir/cortical.envelope"

	# Preserve every non-cortical atlas label, including ventricles,
	# subcortical GM, cerebellum, brainstem and corpus callosum.
	fslmaths "$hybrid_dir/cortical.envelope" -binv "$hybrid_dir/noncortical.mask"
	fslmaths "$hybrid_dir/atlas.nii.gz" -mas "$hybrid_dir/noncortical.mask" \
		"$hybrid_dir/protected.labels"
	fslmaths "$hybrid_dir/protected.labels" -bin "$hybrid_dir/protected.mask"

	# Assign newly introduced DL WM voxels to the nearest atlas hemisphere.
	distancemap -i "$hybrid_dir/lh.cortex" -o "$hybrid_dir/lh.distance"
	distancemap -i "$hybrid_dir/rh.cortex" -o "$hybrid_dir/rh.distance"
	# rh.distance - lh.distance is positive where a voxel is closer to
	# the left cortical envelope. FSL -bin only retains positive values;
	# binarizing a negative-valued comparison would erase the LH territory.
	fslmaths "$hybrid_dir/rh.distance" -sub "$hybrid_dir/lh.distance" \
		-thr 0 -bin "$hybrid_dir/lh.territory"
	fslmaths "$hybrid_dir/lh.territory" -binv "$hybrid_dir/rh.territory"

	# Exclude protected atlas structures from the DL cortical-WM mask.
	fslmaths "$hybrid_dir/protected.mask" -binv \
		-mul "$FS_FIX_WM/wm_replaced_1mm.nii.gz" -bin "$hybrid_dir/dl.cortical.wm"

	# Keep the warped cortical envelope, extending it only where the DL WM
	# itself extends beyond the atlas. Atlas-WM voxels not supported by DL
	# WM become cortical GM; this is the white-surface-changing operation.
	fslmaths "$hybrid_dir/cortical.envelope" -max "$hybrid_dir/dl.cortical.wm" \
		-bin "$hybrid_dir/hybrid.cortical.envelope"
	fslmaths "$hybrid_dir/hybrid.cortical.envelope" \
		-sub "$hybrid_dir/dl.cortical.wm" -thr 0.5 -bin "$hybrid_dir/hybrid.gm"

	fslmaths "$hybrid_dir/dl.cortical.wm" -mul "$hybrid_dir/lh.territory" \
		-mul 2 "$hybrid_dir/lh.wm"
	fslmaths "$hybrid_dir/dl.cortical.wm" -mul "$hybrid_dir/rh.territory" \
		-mul 41 "$hybrid_dir/rh.wm"
	fslmaths "$hybrid_dir/hybrid.gm" -mul "$hybrid_dir/lh.territory" \
		-mul 3 "$hybrid_dir/lh.gm"
	fslmaths "$hybrid_dir/hybrid.gm" -mul "$hybrid_dir/rh.territory" \
		-mul 42 "$hybrid_dir/rh.gm"

	fslmaths "$hybrid_dir/protected.labels" \
		-add "$hybrid_dir/lh.wm" -add "$hybrid_dir/rh.wm" \
		-add "$hybrid_dir/lh.gm" -add "$hybrid_dir/rh.gm" \
		"$hybrid_dir/aseg.presurf.hybrid.nii.gz" -odt char
	fslmaths "$hybrid_dir/atlas.nii.gz" \
		-sub "$hybrid_dir/aseg.presurf.hybrid.nii.gz" -abs -bin \
		"$hybrid_dir/atlas_vs_hybrid.changed_mask.nii.gz"
	mri_convert -ns 1 -odt uchar "$hybrid_dir/aseg.presurf.hybrid.nii.gz" \
		"$FS_MRI_DIR/aseg.presurf.hybrid.mgz"
	cp "$FS_MRI_DIR/aseg.presurf.hybrid.mgz" "$FS_MRI_DIR/aseg.presurf.mgz"
	log "[HYBRID ASEG] Selected aseg.presurf.hybrid.mgz"
}

prepare_chimpanzee_gca_aseg() {
	local chimp_dir="$FS_FIX_WM/chimpanzee_gca"
	mkdir -p "$chimp_dir"

	# Chimpanzee has no compatible whole-brain label atlas to warp. Retain
	# the GCA segmentation, but apply the historical claustrum relabeling
	# before normalization and WM construction so all downstream volumes
	# consume the same aseg. If labels 138/139 are absent, this is a no-op.
	log "[CHIMP GCA] Prepare GCA aseg and claustrum correction"
	cp "$FS_MRI_DIR/aseg.presurf.mgz" "$FS_MRI_DIR/aseg.presurf.gca.mgz"
	mri_convert "$FS_MRI_DIR/aseg.presurf.gca.mgz" "$chimp_dir/aseg.gca.nii.gz"

	fslmaths "$chimp_dir/aseg.gca.nii.gz" -thr 138 -uthr 138 -bin \
		"$chimp_dir/lh.claustrum.nii.gz"
	fslmaths "$chimp_dir/aseg.gca.nii.gz" -thr 139 -uthr 139 -bin \
		"$chimp_dir/rh.claustrum.nii.gz"
	fslmaths "$chimp_dir/lh.claustrum.nii.gz" \
		-add "$chimp_dir/rh.claustrum.nii.gz" -bin \
		"$chimp_dir/claustrum.mask.nii.gz"

	local claustrum_voxels
	claustrum_voxels="$(fslstats "$chimp_dir/claustrum.mask.nii.gz" -V | awk '{print $1}')"
	if [[ $claustrum_voxels -eq 0 ]]; then
		log "[CHIMP GCA] Labels 138/139 absent; claustrum correction is a no-op"
		# Keep the final aseg representation consistent with the corrected
		# claustrum branch. Preprocess_3_2.sh supplies an explicit CC seed
		# for every species to avoid the FreeSurfer 7.2/7.4 mri_fill
		# automatic segmentation-seed path.
		mri_convert -ns 1 -odt uchar "$FS_MRI_DIR/aseg.presurf.gca.mgz" \
			"$FS_MRI_DIR/aseg.presurf.mgz"
		return
	fi
	CHIMP_CLAUSTRUM_AVAILABLE=1

	fslmaths "$chimp_dir/claustrum.mask.nii.gz" -binv \
		-mul "$chimp_dir/aseg.gca.nii.gz" \
		"$chimp_dir/aseg.no_claustrum.nii.gz"
	fslmaths "$chimp_dir/lh.claustrum.nii.gz" -mul 12 \
		"$chimp_dir/lh.claustrum_as_putamen.nii.gz"
	fslmaths "$chimp_dir/rh.claustrum.nii.gz" -mul 51 \
		"$chimp_dir/rh.claustrum_as_putamen.nii.gz"
	fslmaths "$chimp_dir/aseg.no_claustrum.nii.gz" \
		-add "$chimp_dir/lh.claustrum_as_putamen.nii.gz" \
		-add "$chimp_dir/rh.claustrum_as_putamen.nii.gz" \
		"$chimp_dir/aseg.presurf.corrected.nii.gz" -odt char
	mri_convert -ns 1 -odt uchar "$chimp_dir/aseg.presurf.corrected.nii.gz" \
		"$FS_MRI_DIR/aseg.presurf.mgz"
}

# =====================================================================
# STEP 4 | Select the final aseg source
# =====================================================================
if [[ $SPECIES == "Macaque" || $SPECIES == "Marmoset" ]]; then
	if [[ $SPECIES == "Macaque" ]]; then
		NMT_REF="$TEMPLATE_DIR/NMT_brain.nii.gz"
		FS_ATLAS="$TEMPLATE_DIR/labes_fs_with_thalamus.nii.gz"
	else
		NMT_REF="$TEMPLATE_DIR/RIKENMarmoset15_AverageT1w_restore_dedrift_brain.nii.gz"
		FS_ATLAS="$TEMPLATE_DIR/Avgwmparc.nii.gz"
	fi

	warp_species_atlas_to_fs
	if prepare_dl_wm_in_fs_space; then
		if (( USE_HYBRID_ASEG )); then
			build_hybrid_aseg
		else
			log "[HYBRID ASEG] Disabled; using pure warped atlas"
			log "[HYBRID ASEG] Selected aseg.presurf.atlas.mgz"
		fi
	elif (( USE_HYBRID_ASEG )); then
		warn "wm.nii.gz not found; hybrid aseg unavailable, using pure warped atlas"
		log "[HYBRID ASEG] Selected aseg.presurf.atlas.mgz"
	fi
else
	# Chimpanzee has no compatible whole-brain FS-label atlas in the
	# repository, so retain the species-specific GCA segmentation path.
	log "[4] Run GCA segmentation for Chimpanzee"
	log "[HYBRID ASEG] Not applicable to Chimpanzee; using GCA aseg"
	mri_ca_register -threads "$THREADS" \
		-nobigventricles -T "$FS_MRI_DIR/transforms/talairach.lta" \
		-align-after -mask "$FS_MRI_DIR/brainmask.mgz" \
		"$FS_MRI_DIR/norm.mgz" "$GCA" "$FS_MRI_DIR/transforms/talairach.m3z"
	mri_ca_label -threads "$THREADS" \
		-relabel_unlikely 9 .3 -prior 0.5 -align "$FS_MRI_DIR/norm.mgz" \
		"$FS_MRI_DIR/transforms/talairach.m3z" "$GCA" \
		"$FS_MRI_DIR/aseg.auto_noCCseg.mgz"
	mri_cc -aseg aseg.auto_noCCseg.mgz -o aseg.auto.mgz \
		-lta "$FS_MRI_DIR/transforms/cc_up.lta" "$SUB_ID"
	cp "$FS_MRI_DIR/aseg.auto.mgz" "$FS_MRI_DIR/aseg.presurf.mgz"
	prepare_chimpanzee_gca_aseg
	prepare_dl_wm_in_fs_space || true
fi

# Generate the final intensity volumes only after selecting the final aseg.
mri_normalize -seed 1234 -mprage \
	-aseg "$FS_MRI_DIR/aseg.presurf.mgz" -mask "$FS_MRI_DIR/brainmask.mgz" \
	"$FS_MRI_DIR/norm.mgz" "$FS_MRI_DIR/brain.mgz"
mri_mask "$FS_MRI_DIR/brain.mgz" "$FS_MRI_DIR/brainmask.mgz" \
	"$FS_MRI_DIR/brain.finalsurfs.mgz"

# =====================================================================
# STEP 5 | Macaque-specific ventricle and claustrum intensity fixes
# =====================================================================
if [[ $SPECIES == "Macaque" ]]; then
	log "[5] Apply Macaque BG / claustrum / ventricle intensity fixes"
	MASK_BG="$TEMPLATE_DIR/gb_mod.nii.gz"
	MASK_CLA="$TEMPLATE_DIR/claustros.nii.gz"
	WarpImageMultiTransform 3 "$MASK_BG" "$FS_FIX_WM/bg_ventricules.nii.gz" \
		-R "$REF_IMG" "$W1" "$AFF_TXT" --use-NN
	WarpImageMultiTransform 3 "$MASK_CLA" "$FS_FIX_WM/claustro.native.nii.gz" \
		-R "$REF_IMG" "$W1" "$AFF_TXT" --use-NN

	fslmaths "$FS_FIX_WM/claustro.native.nii.gz" -mul 30 -fmean \
		"$FS_FIX_WM/claustro.native.nii.gz"
	fslmaths "$FS_FIX_WM/bg_ventricules.nii.gz" -dilM -fmean \
		"$FS_FIX_WM/bg_ventricules_smooth.nii.gz"
	fslmaths "$FS_FIX_WM/bg_ventricules_smooth.nii.gz" -binv \
		"$FS_FIX_WM/bg_ventricules_binv_smooth.nii.gz"

	flirt -ref "$FS_FIX_BM/FS_brain.nii.gz" \
		-in "$FS_FIX_WM/bg_ventricules_binv_smooth.nii.gz" \
		-applyxfm -init "$FS_FIX_WM/brain_for_fix_fs.mat" \
		-out "$FS_FIX_WM/bg_ventricules_smooth_binv_fs_space.nii.gz"
	flirt -ref "$FS_FIX_BM/FS_brain.nii.gz" \
		-in "$FS_FIX_WM/claustro.native.nii.gz" \
		-applyxfm -init "$FS_FIX_WM/brain_for_fix_fs.mat" \
		-out "$FS_FIX_WM/claustro.nii.gz" -interp nearestneighbour

	python3 "$PY_UTIL" "$FS_FIX_WM" \
		bg_ventricules_smooth_binv_fs_space.nii.gz 1mm \
		bg_ventricules_smooth_binv_fs_space
	python3 "$PY_UTIL" "$FS_FIX_WM" claustro.nii.gz 1mm claustro

	cp "$FS_MRI_DIR/brain.mgz" "$FS_MRI_DIR/brain_orig.mgz"
	cp "$FS_MRI_DIR/norm.mgz" "$FS_MRI_DIR/norm_orig.mgz"
	mri_convert "$FS_MRI_DIR/brain_orig.mgz" "$FS_MRI_DIR/brain_orig.nii.gz"
	mri_convert "$FS_MRI_DIR/norm_orig.mgz" "$FS_MRI_DIR/norm_orig.nii.gz"
	fslmaths "$FS_FIX_WM/bg_ventricules_smooth_binv_fs_space_1mm.nii.gz" \
		-mul "$FS_MRI_DIR/brain_orig.nii.gz" "$FS_MRI_DIR/brain.nii.gz"
	fslmaths "$FS_FIX_WM/bg_ventricules_smooth_binv_fs_space_1mm.nii.gz" \
		-mul "$FS_MRI_DIR/norm_orig.nii.gz" "$FS_MRI_DIR/norm.nii.gz"
	fslmaths "$FS_MRI_DIR/brain.nii.gz" -add "$FS_FIX_WM/claustro_1mm.nii.gz" \
		"$FS_MRI_DIR/brain.nii.gz"
	fslmaths "$FS_MRI_DIR/norm.nii.gz" -add "$FS_FIX_WM/claustro_1mm.nii.gz" \
		"$FS_MRI_DIR/norm.nii.gz"
	mri_convert "$FS_MRI_DIR/brain.nii.gz" "$FS_MRI_DIR/brain.mgz"
	mri_convert "$FS_MRI_DIR/norm.nii.gz" "$FS_MRI_DIR/norm.mgz"
	cp "$FS_MRI_DIR/brain.mgz" "$FS_MRI_DIR/brain.finalsurfs.mgz"
fi

# =====================================================================
# STEP 6 | Build wm.mgz, preferring the registered DL WM
# =====================================================================
log "[6] Build final WM volume"
if (( DL_WM_AVAILABLE )); then
	WM_SEED="$FS_FIX_WM/wm_dl_111.mgz"
	if [[ $SPECIES == "Chimpanzee" && $CHIMP_CLAUSTRUM_AVAILABLE -eq 1 ]]; then
		# Preserve the historical claustrum-in-WM repair, but include it in
		# the seed before mri_edit_wm_with_aseg and mri_pretess.
		CHIMP_GCA_DIR="$FS_FIX_WM/chimpanzee_gca"
		fslmaths "$CHIMP_GCA_DIR/claustrum.mask.nii.gz" -mul 250 \
			-max "$FS_FIX_WM/wm_dl_111.nii.gz" \
			"$CHIMP_GCA_DIR/wm_dl_with_claustrum.nii.gz"
		mri_convert -ns 1 -odt uchar \
			"$CHIMP_GCA_DIR/wm_dl_with_claustrum.nii.gz" \
			"$CHIMP_GCA_DIR/wm_dl_with_claustrum.mgz"
		WM_SEED="$CHIMP_GCA_DIR/wm_dl_with_claustrum.mgz"
	fi
	# The DL mask is an automatic input segmentation, not a set of manual
	# WM edits. Do not use -keep-in: that option restores reserved values
	# 255/1 after automatic editing and would make DL predictions immutable.
	mri_edit_wm_with_aseg "$WM_SEED" \
		"$FS_MRI_DIR/brain.mgz" "$FS_MRI_DIR/aseg.presurf.mgz" \
		"$FS_MRI_DIR/wm.asegedit.mgz"
else
	warn "wm.nii.gz not found — falling back to FreeSurfer WM segmentation"
	mri_segment -mprage "$FS_MRI_DIR/brain.mgz" "$FS_MRI_DIR/wm.seg.mgz"
	mri_edit_wm_with_aseg -keep-in "$FS_MRI_DIR/wm.seg.mgz" \
		"$FS_MRI_DIR/brain.mgz" "$FS_MRI_DIR/aseg.presurf.mgz" \
		"$FS_MRI_DIR/wm.asegedit.mgz"
fi
mri_pretess "$FS_MRI_DIR/wm.asegedit.mgz" wm \
	"$FS_MRI_DIR/norm.mgz" "$FS_MRI_DIR/wm.mgz"

log "Pipeline finished successfully 🎉"
