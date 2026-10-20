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
# MarmosetPialRefinement.sh
#
# Marmoset-only, T1-only pial-surface refinement for PrimateX.
#
# The script deliberately separates final white-surface placement from pial
# estimation:
#   1. Reproduce the previous PrimateX final white/pial pass with the original
#      brain.finalsurfs volume and retain it with a .default suffix.
#   2. Promote only its white surface as the unchanged final white surface.
#   3. Create a pial-specific T1 using conservative N4 bias correction and
#      robust WM-median normalization.
#   4. Estimate a first pial candidate from subject-specific class statistics
#      (-mode 0), rather than FreeSurfer's fixed class-mode override.
#   5. Estimate a local cortical-GM correction field from that candidate's
#      ribbon and run a second, pial-only refinement.
#   6. Promote the second candidate only after basic surface QC succeeds.
#
# No T2w image is required. Intermediate images, candidate surfaces and QC
# metrics are retained for inspection.
#
# Methodological reference:
# https://github.com/Washington-University/NHPPipelines/blob/master/FreeSurfer/scripts/FreeSurferHiresPialNHP.sh
# In that script, Takuya Hayashi's 2016/2018 comments document the need for
# stronger Marmoset pial expansion settings, a specially bias-corrected first
# T1 pass, and cortical-ribbon gray-intensity normalization. This implementation
# adapts those T1 components to PrimateX without copying its T2 refinement.
# -----------------------------------------------------------------------------
set -euo pipefail

usage() {
	cat <<'EOF'
Usage:
  MarmosetPialRefinement.sh \
    --subject <SUB_ID> \
    --subjects-dir <SUBJECTS_DIR> \
    [--threads <N>]

Options:
  --subject       FreeSurfer subject ID.
  --subjects-dir  FreeSurfer SUBJECTS_DIR containing the subject.
  --threads       Threads passed only to commands with an explicit interface
                  (mris_make_surfaces -openmp). Default: 1.
EOF
}

log()  { printf '\e[1;36m[Marmoset pial] %s\e[0m\n' "$*"; }
warn() { printf '\e[1;33m[Marmoset pial WARNING] %s\e[0m\n' "$*" >&2; }
err()  { printf '\e[1;31m[Marmoset pial ERROR] %s\e[0m\n' "$*" >&2; exit 1; }

require_command() {
	command -v "$1" >/dev/null 2>&1 || err "Required command not found: $1"
}

require_file() {
	[[ -f $1 ]] || err "Required file not found: $1"
}

mask_voxels() {
	local count
	count=$(fslstats "$1" -V | awk 'NR == 1 {print int($1)}')
	[[ $count =~ ^[0-9]+$ ]] || err "Could not read mask voxel count: $1"
	printf '%s\n' "$count"
}

positive_number() {
	awk -v value="$1" 'BEGIN { exit !(value + 0 > 0) }'
}

surface_metric() {
	local surface=$1
	local metric=$2
	# Consume the complete mris_info stream. Exiting awk at the first match can
	# send SIGPIPE to mris_info and make the pipeline fail under pipefail.
	mris_info "$surface" \
		| awk -v metric="$metric" '$1 == metric {value=$2} END {if (value != "") print value}'
}

surface_intersecting_vertices() {
	local surface=$1
	local output
	local count

	# FreeSurfer 7.2 does not include num_intersecting_faces in the ordinary
	# mris_info report. Its stable interface is --intersections, where the
	# reported number is the count of vertices belonging to intersecting faces.
	output=$(mris_info --intersections "$surface")
	count=$(awk '
		$1 == "Found" && $2 ~ /^[0-9]+$/ && $3 == "intersections" {value=$2}
		END {if (value != "") print value}
	' <<< "$output")
	[[ $count =~ ^[0-9]+$ ]] \
		|| err "Could not read intersecting-vertex count: $surface"
	printf '%s\n' "$count"
}

SUB_ID=""
SUBJECTS_ROOT=""
THREADS=1

while [[ $# -gt 0 ]]; do
	case "$1" in
		--subject|-id)
			SUB_ID="${2:?missing subject ID}"
			shift 2
			;;
		--subjects-dir)
			SUBJECTS_ROOT="${2:?missing SUBJECTS_DIR}"
			shift 2
			;;
		--threads|-threads)
			THREADS="${2:?missing thread count}"
			shift 2
			;;
		-h|--help)
			usage
			exit 0
			;;
		*)
			err "Unknown option: $1"
			;;
	esac
done

[[ -n $SUB_ID ]] || err "--subject is required"
[[ -n $SUBJECTS_ROOT ]] || err "--subjects-dir is required"
[[ $THREADS =~ ^[1-9][0-9]*$ ]] || err "--threads must be a positive integer"

for command_name in \
	N4BiasFieldCorrection fslmaths fslstats mri_convert \
	mris_info mris_make_surfaces mris_volmask; do
	require_command "$command_name"
done

export SUBJECTS_DIR="$SUBJECTS_ROOT"

FS_SUB_DIR="$SUBJECTS_DIR/$SUB_ID"
FS_MRI_DIR="$FS_SUB_DIR/mri"
FS_SURF_DIR="$FS_SUB_DIR/surf"
WORK_DIR="$FS_MRI_DIR/marmoset_pial"

ORIG_MGZ="$FS_MRI_DIR/orig.mgz"
BRAINMASK_MGZ="$FS_MRI_DIR/brainmask.mgz"
BASE_T1_MGZ="$FS_MRI_DIR/brain.finalsurfs.mgz"
ASEG_MGZ="$FS_MRI_DIR/aseg.presurf.mgz"
WM_MGZ="$FS_MRI_DIR/wm.mgz"
FILLED_MGZ="$FS_MRI_DIR/filled.mgz"
DL_WM_NII="$FS_MRI_DIR/fix_wm/wm_replaced_1mm.nii.gz"

for input_file in \
	"$ORIG_MGZ" "$BRAINMASK_MGZ" "$BASE_T1_MGZ" \
	"$ASEG_MGZ" "$WM_MGZ" "$FILLED_MGZ" \
	"$FS_SURF_DIR/lh.white.preaparc" "$FS_SURF_DIR/rh.white.preaparc"; do
	require_file "$input_file"
done

mkdir -p "$WORK_DIR"

# These values are expressed in the enlarged 1 mm FreeSurfer workspace.
# They correspond to the dedicated NHPPipelines Marmoset surface settings.
PIAL_ARGS=(
	-variablesigma 8
	-psigma 10
	-max 20
)

# Keep the large Marmoset search range for regions that require substantial
# outward deformation, but prevent the occipital pial surface from treating
# adjacent cerebellar tissue as cerebral cortex. With -aseg loaded,
# -erase_cerebellum sets aseg labels 7/8/46/47 to zero in the internal T1 used
# for surface placement. Apply this only to the pial-only candidates so the
# reference pass and promoted white surface remain unchanged.
PIAL_ANATOMICAL_CONSTRAINT_ARGS=(
	-erase_cerebellum
)

# Reviewable parameters for the Marmoset-only intensity steps.
# Distances/sigmas are in the enlarged 1 mm FreeSurfer workspace. The initial
# N4 B-spline spacing is an empirical PrimateX value, not a species-specific
# parameter supplied by NHPPipelines.
N4_SPLINE_DISTANCE=50
GM_SMOOTH_SIGMA=5
GM_FIELD_MIN=0.8
GM_FIELD_MAX=1.2
# mris_info --intersections counts marked vertices, not intersecting faces.
# These tolerances preserve the prior 100-face/+20-face intent using the
# conservative upper bound of three vertices per triangular face.
MAX_INTERSECTING_VERTICES_BASE=300
MAX_INTERSECTING_VERTICES_INCREASE=60

SURFACE_INPUT_ARGS=(
	-noaparc
	-aseg aseg.presurf
	-filled filled
	-wm wm
	-mgz
)

log "Preparing the Marmoset-only T1 volume for pial estimation"

ORIG_NII="$WORK_DIR/orig.float.nii.gz"
BRAINMASK_FLOAT_NII="$WORK_DIR/brainmask.float.nii.gz"
BRAIN_MASK_NII="$WORK_DIR/brainmask.bin.nii.gz"
ASEG_NII="$WORK_DIR/aseg.presurf.nii.gz"

mri_convert -odt float "$ORIG_MGZ" "$ORIG_NII"
mri_convert -odt float "$BRAINMASK_MGZ" "$BRAINMASK_FLOAT_NII"
mri_convert -ns 1 -odt float "$ASEG_MGZ" "$ASEG_NII"
fslmaths "$BRAINMASK_FLOAT_NII" -bin "$BRAIN_MASK_NII" -odt char

# Prefer the registered DL WM segmentation as a robust intensity sample. It is
# used only as an intensity-normalization mask here; it is not converted into
# FreeSurfer's reserved manual-edit values.
WM_SEED_NII="$WORK_DIR/wm.seed.nii.gz"
if [[ -f $DL_WM_NII ]]; then
	log "Using the registered DL WM mask to estimate the WM intensity"
	fslmaths "$DL_WM_NII" -bin "$WM_SEED_NII" -odt char
else
	warn "DL WM mask not found; using aseg labels 2 and 41 for WM intensity sampling"
	fslmaths "$ASEG_NII" -thr 2 -uthr 2 -bin "$WORK_DIR/wm.label2.nii.gz"
	fslmaths "$ASEG_NII" -thr 41 -uthr 41 -bin "$WORK_DIR/wm.label41.nii.gz"
	fslmaths "$WORK_DIR/wm.label2.nii.gz" \
		-add "$WORK_DIR/wm.label41.nii.gz" -bin "$WM_SEED_NII" -odt char
fi

WM_SEED_VOXELS=$(mask_voxels "$WM_SEED_NII")
if (( WM_SEED_VOXELS < 1000 )); then
	warn "Atlas/DL WM seed is too small ($WM_SEED_VOXELS voxels); falling back to wm.mgz"
	mri_convert -odt float "$WM_MGZ" "$WORK_DIR/wm.mgz.float.nii.gz"
	fslmaths "$WORK_DIR/wm.mgz.float.nii.gz" -bin "$WM_SEED_NII" -odt char
	WM_SEED_VOXELS=$(mask_voxels "$WM_SEED_NII")
fi
(( WM_SEED_VOXELS >= 1000 )) || err "Could not construct a valid WM intensity mask"

# Erosion reduces partial-volume contamination. Use the strongest erosion that
# still leaves a sufficiently large sample.
fslmaths "$WM_SEED_NII" -ero "$WORK_DIR/wm.core.ero1.nii.gz" -odt char
fslmaths "$WORK_DIR/wm.core.ero1.nii.gz" -ero "$WORK_DIR/wm.core.ero2.nii.gz" -odt char

WM_CORE_NII="$WORK_DIR/wm.core.ero2.nii.gz"
WM_CORE_VOXELS=$(mask_voxels "$WM_CORE_NII")
if (( WM_CORE_VOXELS < 1000 )); then
	WM_CORE_NII="$WORK_DIR/wm.core.ero1.nii.gz"
	WM_CORE_VOXELS=$(mask_voxels "$WM_CORE_NII")
fi
if (( WM_CORE_VOXELS < 1000 )); then
	WM_CORE_NII="$WM_SEED_NII"
	WM_CORE_VOXELS=$WM_SEED_VOXELS
fi
(( WM_CORE_VOXELS >= 1000 )) || err "Could not construct a valid WM core mask"

# This N4 pass is intentionally pial-specific. It does not replace orig.mgz,
# norm.mgz, brain.mgz or brain.finalsurfs.mgz used by other species/stages.
# Retain an initial B-spline spacing of 50 as an empirical starting value in
# the enlarged workspace. Weight the fit with the eroded WM core so that N4
# estimates a smooth receive-field variation from a relatively homogeneous
# tissue class instead of absorbing the central-WM/peripheral-GM contrast into
# the bias field. The brain mask still defines the region receiving correction;
# the WM core is a fitting weight only and does not restrict the output to WM.
N4_RAW_NII="$WORK_DIR/T1.n4.raw.nii.gz"
N4_BIAS_NII="$WORK_DIR/T1.n4.bias.nii.gz"
log "Running N4 with the WM core as the bias-field fitting weight"
N4BiasFieldCorrection \
	-d 3 \
	-i "$ORIG_NII" \
	-x "$BRAIN_MASK_NII" \
	-w "$WM_CORE_NII" \
	-s 2 \
	-b "[$N4_SPLINE_DISTANCE]" \
	-c "[50x50x30x20,1e-7]" \
	-o "[$N4_RAW_NII,$N4_BIAS_NII]"

WM_MEDIAN_N4=$(fslstats "$N4_RAW_NII" -k "$WM_CORE_NII" -P 50)
positive_number "$WM_MEDIAN_N4" || err "Invalid N4 WM median: $WM_MEDIAN_N4"
WM_SCALE_N4=$(awk -v median="$WM_MEDIAN_N4" 'BEGIN {printf "%.10f", 110.0 / median}')

PIAL_T1_NII="$WORK_DIR/T1.n4.wm110.nii.gz"
PIAL_T1_MGZ="$WORK_DIR/T1.n4.wm110.mgz"
fslmaths "$N4_RAW_NII" -mul "$WM_SCALE_N4" -mas "$BRAIN_MASK_NII" \
	"$PIAL_T1_NII" -odt float
mri_convert -odt float "$PIAL_T1_NII" "$PIAL_T1_MGZ"

log "Saving the previous PrimateX white/pial result as the .default reference"
for hemi in lh rh; do
	mris_make_surfaces \
		-openmp "$THREADS" \
		"${PIAL_ARGS[@]}" \
		-orig_white white.preaparc \
		"${SURFACE_INPUT_ARGS[@]}" \
		-T1 brain.finalsurfs \
		-output .default \
		"$SUB_ID" "$hemi"
	require_file "$FS_SURF_DIR/${hemi}.white.default"
	require_file "$FS_SURF_DIR/${hemi}.pial.default"

	# The .default white is produced by the same command and T1 volume as the
	# previous pipeline. New intensity correction is therefore restricted to
	# pial estimation and cannot move the final white surface.
	cp -p "$FS_SURF_DIR/${hemi}.white.default" "$FS_SURF_DIR/${hemi}.white"
	for scalar_name in area curv; do
		if [[ -f $FS_SURF_DIR/${hemi}.${scalar_name}.default ]]; then
			cp -p "$FS_SURF_DIR/${hemi}.${scalar_name}.default" \
				"$FS_SURF_DIR/${hemi}.${scalar_name}"
		fi
	done
	if [[ -f $FS_SUB_DIR/label/${hemi}.cortex.default.label ]]; then
		cp -p "$FS_SUB_DIR/label/${hemi}.cortex.default.label" \
			"$FS_SUB_DIR/label/${hemi}.cortex.label"
	fi
done

log "Estimating the first N4/mode-0 pial candidate"
for hemi in lh rh; do
	# Do not set -orig_pial here. Leaving it unset is intentional: the first
	# candidate starts at the final white surface and retains FreeSurfer's
	# initial smooth outward deformation.
	mris_make_surfaces \
		-openmp "$THREADS" \
		-mode 0 \
		"${PIAL_ARGS[@]}" \
		"${PIAL_ANATOMICAL_CONSTRAINT_ARGS[@]}" \
		-nowhite \
		-orig_white white \
		"${SURFACE_INPUT_ARGS[@]}" \
		-T1 marmoset_pial/T1.n4.wm110 \
		-output .pre_graynorm \
		"$SUB_ID" "$hemi"
	require_file "$FS_SURF_DIR/${hemi}.pial.pre_graynorm"
done

log "Building a ribbon from the first pial candidate"
RIBBON_ROOT="ribbon.marmoset_pre_graynorm"
mris_volmask \
	--sd "$SUBJECTS_DIR" \
	--surf_white white \
	--surf_pial pial.pre_graynorm \
	--aseg_name aseg.presurf \
	--label_left_white 2 \
	--label_left_ribbon 3 \
	--label_right_white 41 \
	--label_right_ribbon 42 \
	--out_root "$RIBBON_ROOT" \
	--save_ribbon \
	"$SUB_ID"

RIBBON_SOURCE_MGZ="$FS_MRI_DIR/${RIBBON_ROOT}.mgz"
RIBBON_MGZ="$WORK_DIR/ribbon.pre_graynorm.mgz"
require_file "$RIBBON_SOURCE_MGZ"
mv -f "$RIBBON_SOURCE_MGZ" "$RIBBON_MGZ"
for hemi in lh rh; do
	if [[ -f $FS_MRI_DIR/${hemi}.${RIBBON_ROOT}.mgz ]]; then
		mv -f "$FS_MRI_DIR/${hemi}.${RIBBON_ROOT}.mgz" \
			"$WORK_DIR/${hemi}.ribbon.pre_graynorm.mgz"
	fi
done

RIBBON_NII="$WORK_DIR/ribbon.pre_graynorm.nii.gz"
mri_convert -ns 1 -odt uchar "$RIBBON_MGZ" "$RIBBON_NII"

# The combined ribbon contains white labels 2/41 and cortical-GM labels 3/42.
# Only the cortical-GM portion is used to estimate the local correction field.
fslmaths "$RIBBON_NII" -thr 3 -uthr 3 -bin "$WORK_DIR/gm.label3.nii.gz"
fslmaths "$RIBBON_NII" -thr 42 -uthr 42 -bin "$WORK_DIR/gm.label42.nii.gz"
fslmaths "$WORK_DIR/gm.label3.nii.gz" -add "$WORK_DIR/gm.label42.nii.gz" \
	-bin "$WORK_DIR/gm.ribbon.nii.gz" -odt char
fslmaths "$WORK_DIR/gm.ribbon.nii.gz" -ero "$WORK_DIR/gm.ribbon.eroded.nii.gz" -odt char

GM_CORE_NII="$WORK_DIR/gm.ribbon.eroded.nii.gz"
GM_CORE_VOXELS=$(mask_voxels "$GM_CORE_NII")
if (( GM_CORE_VOXELS < 1000 )); then
	warn "Eroded GM ribbon is small ($GM_CORE_VOXELS voxels); using the un-eroded ribbon"
	GM_CORE_NII="$WORK_DIR/gm.ribbon.nii.gz"
	GM_CORE_VOXELS=$(mask_voxels "$GM_CORE_NII")
fi
(( GM_CORE_VOXELS >= 1000 )) || err "First-pass ribbon did not yield a valid GM sample"

# Exclude the extreme intensity tails before estimating the local GM mean.
GM_P05=$(fslstats "$PIAL_T1_NII" -k "$GM_CORE_NII" -P 5)
GM_P95=$(fslstats "$PIAL_T1_NII" -k "$GM_CORE_NII" -P 95)
awk -v low="$GM_P05" -v high="$GM_P95" \
	'BEGIN {exit !(low + 0 > 0 && high + 0 > low + 0)}' \
	|| err "Invalid GM robust range: p05=$GM_P05 p95=$GM_P95"

GM_ROBUST_NII="$WORK_DIR/gm.ribbon.robust.nii.gz"
fslmaths "$PIAL_T1_NII" -thr "$GM_P05" -uthr "$GM_P95" -bin \
	-mas "$GM_CORE_NII" "$GM_ROBUST_NII" -odt char
GM_ROBUST_VOXELS=$(mask_voxels "$GM_ROBUST_NII")
(( GM_ROBUST_VOXELS >= 1000 )) || err "Robust GM sample is too small"

GM_GLOBAL_MEDIAN=$(fslstats "$PIAL_T1_NII" -k "$GM_ROBUST_NII" -P 50)
positive_number "$GM_GLOBAL_MEDIAN" || err "Invalid GM median: $GM_GLOBAL_MEDIAN"
GM_GLOBAL_INVERSE=$(awk -v median="$GM_GLOBAL_MEDIAN" \
	'BEGIN {printf "%.10f", 1.0 / median}')
positive_number "$GM_GLOBAL_INVERSE" || \
	err "Invalid inverse GM median: $GM_GLOBAL_INVERSE"

# Mask-aware Gaussian smoothing:
#   local GM mean = smooth(T1 * GMmask) / smooth(GMmask)
# Sigma=5 is specified in the enlarged 1 mm FreeSurfer workspace, following
# the scale used by the Marmoset NHPPipelines refinement.
fslmaths "$GM_ROBUST_NII" -s "$GM_SMOOTH_SIGMA" \
	"$WORK_DIR/gm.weight.smooth.nii.gz" -odt float
fslmaths "$PIAL_T1_NII" -mul "$GM_ROBUST_NII" -s "$GM_SMOOTH_SIGMA" \
	"$WORK_DIR/gm.intensity.smooth.nii.gz" -odt float
fslmaths "$WORK_DIR/gm.weight.smooth.nii.gz" -max 0.01 \
	"$WORK_DIR/gm.weight.smooth.safe.nii.gz" -odt float
fslmaths "$WORK_DIR/gm.weight.smooth.nii.gz" -thr 0.01 -bin \
	"$WORK_DIR/gm.local.valid.nii.gz" -odt char
fslmaths "$WORK_DIR/gm.intensity.smooth.nii.gz" \
	-div "$WORK_DIR/gm.weight.smooth.safe.nii.gz" \
	"$WORK_DIR/gm.local.mean.nii.gz" -odt float

# Form the local/global GM ratio to suppress low-frequency cortical intensity
# variation. FSL 6 interprets the operand of -div as an image name, so multiply
# by the reciprocal when applying a scalar. Clamp the field to avoid aggressive
# anatomical changes.
fslmaths "$WORK_DIR/gm.local.mean.nii.gz" -mul "$GM_GLOBAL_INVERSE" \
	-max "$GM_FIELD_MIN" -min "$GM_FIELD_MAX" \
	-mas "$WORK_DIR/gm.local.valid.nii.gz" \
	"$WORK_DIR/gm.correction.core.nii.gz" -odt float
fslmaths "$WORK_DIR/gm.correction.core.nii.gz" -dilall -s "$GM_SMOOTH_SIGMA" \
	-max "$GM_FIELD_MIN" -min "$GM_FIELD_MAX" \
	"$WORK_DIR/gm.correction.field.nii.gz" -odt float
fslmaths "$BRAIN_MASK_NII" -binv "$WORK_DIR/outside.brain.nii.gz" -odt char
fslmaths "$WORK_DIR/gm.correction.field.nii.gz" -mas "$BRAIN_MASK_NII" \
	-add "$WORK_DIR/outside.brain.nii.gz" \
	"$WORK_DIR/gm.correction.field.full.nii.gz" -odt float

GREYNORM_RAW_NII="$WORK_DIR/T1.n4.greynorm.raw.nii.gz"
fslmaths "$PIAL_T1_NII" -div "$WORK_DIR/gm.correction.field.full.nii.gz" \
	-mas "$BRAIN_MASK_NII" "$GREYNORM_RAW_NII" -odt float

# Re-anchor WM to 110 after local GM correction so FreeSurfer sees a stable
# global WM reference while the local GM inhomogeneity is reduced.
WM_MEDIAN_GREYNORM=$(fslstats "$GREYNORM_RAW_NII" -k "$WM_CORE_NII" -P 50)
positive_number "$WM_MEDIAN_GREYNORM" \
	|| err "Invalid greynorm WM median: $WM_MEDIAN_GREYNORM"
WM_SCALE_GREYNORM=$(awk -v median="$WM_MEDIAN_GREYNORM" \
	'BEGIN {printf "%.10f", 110.0 / median}')

GREYNORM_T1_NII="$WORK_DIR/T1.n4.greynorm.wm110.nii.gz"
GREYNORM_T1_MGZ="$WORK_DIR/T1.n4.greynorm.wm110.mgz"
fslmaths "$GREYNORM_RAW_NII" -mul "$WM_SCALE_GREYNORM" \
	-mas "$BRAIN_MASK_NII" "$GREYNORM_T1_NII" -odt float
mri_convert -odt float "$GREYNORM_T1_NII" "$GREYNORM_T1_MGZ"

log "Running the second pial-only refinement on the local-GM-normalized T1"
for hemi in lh rh; do
	mris_make_surfaces \
		-openmp "$THREADS" \
		-mode 0 \
		"${PIAL_ARGS[@]}" \
		"${PIAL_ANATOMICAL_CONSTRAINT_ARGS[@]}" \
		-nowhite \
		-orig_white white \
		-orig_pial pial.pre_graynorm \
		"${SURFACE_INPUT_ARGS[@]}" \
		-T1 marmoset_pial/T1.n4.greynorm.wm110 \
		-output .greynorm \
		"$SUB_ID" "$hemi"
	require_file "$FS_SURF_DIR/${hemi}.pial.greynorm"
	for scalar_name in thickness area.pial curv.pial; do
		require_file "$FS_SURF_DIR/${hemi}.${scalar_name}.greynorm"
	done
done

log "Running basic candidate-surface QC"
QC_FILE="$WORK_DIR/qc_summary.tsv"
GM_FIELD_RANGE=$(fslstats "$WORK_DIR/gm.correction.field.nii.gz" \
	-k "$BRAIN_MASK_NII" -R)
{
	printf 'metric\tvalue\n'
	printf 'n4_spline_distance\t%s\n' "$N4_SPLINE_DISTANCE"
	printf 'n4_weight_image\twm_core\n'
	printf 'gm_smooth_sigma\t%s\n' "$GM_SMOOTH_SIGMA"
	printf 'gm_field_min\t%s\n' "$GM_FIELD_MIN"
	printf 'gm_field_max\t%s\n' "$GM_FIELD_MAX"
	printf 'erase_cerebellum\t1\n'
	printf 'max_intersecting_vertices_base\t%s\n' "$MAX_INTERSECTING_VERTICES_BASE"
	printf 'max_intersecting_vertices_increase\t%s\n' "$MAX_INTERSECTING_VERTICES_INCREASE"
	printf 'gm_field_observed_range\t%s\n' "$GM_FIELD_RANGE"
	printf 'wm_seed_voxels\t%s\n' "$WM_SEED_VOXELS"
	printf 'wm_core_voxels\t%s\n' "$WM_CORE_VOXELS"
	printf 'gm_core_voxels\t%s\n' "$GM_CORE_VOXELS"
	printf 'gm_robust_voxels\t%s\n' "$GM_ROBUST_VOXELS"
	printf 'n4_wm_median_before_scaling\t%s\n' "$WM_MEDIAN_N4"
	printf 'n4_wm_scale\t%s\n' "$WM_SCALE_N4"
	printf 'gm_p05\t%s\n' "$GM_P05"
	printf 'gm_p95\t%s\n' "$GM_P95"
	printf 'gm_global_median\t%s\n' "$GM_GLOBAL_MEDIAN"
	printf 'gm_global_inverse\t%s\n' "$GM_GLOBAL_INVERSE"
	printf 'greynorm_wm_median_before_scaling\t%s\n' "$WM_MEDIAN_GREYNORM"
	printf 'greynorm_wm_scale\t%s\n' "$WM_SCALE_GREYNORM"
} > "$QC_FILE"

for hemi in lh rh; do
	WHITE_SURF="$FS_SURF_DIR/${hemi}.white"
	DEFAULT_SURF="$FS_SURF_DIR/${hemi}.pial.default"
	PRE_SURF="$FS_SURF_DIR/${hemi}.pial.pre_graynorm"
	FINAL_SURF="$FS_SURF_DIR/${hemi}.pial.greynorm"

	WHITE_VERTICES=$(surface_metric "$WHITE_SURF" nvertices)
	DEFAULT_VERTICES=$(surface_metric "$DEFAULT_SURF" nvertices)
	PRE_VERTICES=$(surface_metric "$PRE_SURF" nvertices)
	FINAL_VERTICES=$(surface_metric "$FINAL_SURF" nvertices)
	DEFAULT_INTERSECTING_VERTICES=$(surface_intersecting_vertices "$DEFAULT_SURF")
	PRE_INTERSECTING_VERTICES=$(surface_intersecting_vertices "$PRE_SURF")
	FINAL_INTERSECTING_VERTICES=$(surface_intersecting_vertices "$FINAL_SURF")

	[[ $WHITE_VERTICES =~ ^[0-9]+$ ]] || err "Could not read $hemi white vertex count"
	[[ $DEFAULT_VERTICES =~ ^[0-9]+$ ]] || err "Could not read $hemi default vertex count"
	[[ $PRE_VERTICES =~ ^[0-9]+$ ]] || err "Could not read $hemi first-pass vertex count"
	[[ $FINAL_VERTICES =~ ^[0-9]+$ ]] || err "Could not read $hemi final vertex count"

	[[ $WHITE_VERTICES -eq $DEFAULT_VERTICES \
		&& $DEFAULT_VERTICES -eq $PRE_VERTICES \
		&& $PRE_VERTICES -eq $FINAL_VERTICES ]] \
		|| err "$hemi vertex count changed across pial refinement"

	MAX_ALLOWED_INTERSECTING_VERTICES=$((
		PRE_INTERSECTING_VERTICES
		+ MAX_INTERSECTING_VERTICES_INCREASE
	))
	if (( MAX_ALLOWED_INTERSECTING_VERTICES < MAX_INTERSECTING_VERTICES_BASE )); then
		MAX_ALLOWED_INTERSECTING_VERTICES=$MAX_INTERSECTING_VERTICES_BASE
	fi
	(( FINAL_INTERSECTING_VERTICES <= MAX_ALLOWED_INTERSECTING_VERTICES )) \
		|| err "$hemi final pial has $FINAL_INTERSECTING_VERTICES intersecting vertices; allowed $MAX_ALLOWED_INTERSECTING_VERTICES"

	{
		printf '%s_white_vertices\t%s\n' "$hemi" "$WHITE_VERTICES"
		printf '%s_default_intersecting_vertices\t%s\n' \
			"$hemi" "$DEFAULT_INTERSECTING_VERTICES"
		printf '%s_pre_graynorm_intersecting_vertices\t%s\n' \
			"$hemi" "$PRE_INTERSECTING_VERTICES"
		printf '%s_greynorm_intersecting_vertices\t%s\n' \
			"$hemi" "$FINAL_INTERSECTING_VERTICES"
		printf '%s_greynorm_intersecting_vertices_allowed\t%s\n' \
			"$hemi" "$MAX_ALLOWED_INTERSECTING_VERTICES"
	} >> "$QC_FILE"
done

log "QC passed; promoting pial.greynorm to the canonical pial surfaces"
for hemi in lh rh; do
	if [[ -f $FS_SURF_DIR/${hemi}.pial && ! -f $FS_SURF_DIR/${hemi}.pial.before_marmoset_refinement ]]; then
		cp -p "$FS_SURF_DIR/${hemi}.pial" \
			"$FS_SURF_DIR/${hemi}.pial.before_marmoset_refinement"
	fi

	cp -p "$FS_SURF_DIR/${hemi}.pial.greynorm" "$FS_SURF_DIR/${hemi}.pial"

	# Promote pial-derived scalar files. White-derived files are intentionally
	# untouched because they came from the .default reference pass.
	for scalar_name in thickness area.pial curv.pial; do
		cp -p "$FS_SURF_DIR/${hemi}.${scalar_name}.greynorm" \
			"$FS_SURF_DIR/${hemi}.${scalar_name}"
	done
done

log "Marmoset pial refinement completed"
log "Intermediates and QC: $WORK_DIR"
