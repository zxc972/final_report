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
#  Preprocess_3_2.sh  —  Surface reconstruction + spherical registration
# -----------------------------------------------------------------------------
#  Pipeline (macaque‑adapted FreeSurfer)
#  ──────────────────────────────────────
#    1.  Fill WM → create initial left/right orig surfaces (nofix)
#    2.  Smooth, inflate, qsphere → topology fix (mris_fix_topology)
#    3.  Generate white.preaparc + inflated + curvature files
#    4.  Create sphere & register to Buckner40 curvature template
#    5.  Warp additional macaque atlases to subject sphere (optional)
#    6.  Species-specific mris_make_surfaces refinement for pial & final white
#        (Marmoset uses a dedicated T1-only refinement helper)
#    7.  Volumetric ribbon masks & WM / GM sampling (mri_vol2surf)
#
#  Requirements
#    • FreeSurfer (7.x tested)
#    • FSL for flirt (already required in Step 3‑1)
#
#  Usage
#      ./Preprocess_3_2.sh -id <SUB_ID> -out_path <out_path> [-species <name>]
#                          [-threads <N>]
#                          # where <out_path>/<SUB_ID>/ is SUBJECT_DIR
#
#  Options
#      -species <name>   Species name (case-insensitive):
#                        macaque|cynomolgus|rhesus  -> use Macaque templates/logic
#                        chimpanzee
#                        marmoset
#      -threads <N>      Overall thread count for supported FreeSurfer commands.
#                        Must be a positive integer. (Default: 1)
#
#  Example
#      singularity exec -B /data:/data neurotools.sif  \
#           ./Preprocess_3_2.sh -id KM001 -out_path /data/KM001 -species macaque
# -----------------------------------------------------------------------------
#  Author :  Yichun Huang  <ychunhuang@foxmail.com>
#  Updated:  2026-07-24  (Marmoset T1-only pial refinement)
# -----------------------------------------------------------------------------
set -euo pipefail

# ───────────────────── helper fns ────────────────────────────────
usage() { grep -E "^#  " "$0" | cut -c4- ; }
log()   { printf '\e[1;36m[INFO]  %s\e[0m\n'  "$*"; }
err()   { printf '\e[1;31m[ERROR] %s\e[0m\n' "$*" >&2; exit 1; }

# ───────────────────── arg parsing ───────────────────────────────
[[ $# -eq 0 ]] && { err "No arguments provided"; }

SPECIES="Macaque"  # default; -species is case-insensitive: macaque|cynomolgus|rhesus|chimpanzee|marmoset
THREADS=1          # conservative default for reproducibility

while [[ $# -gt 0 ]]; do
    case "$1" in
		-id|--subject)  SUB_ID="${2:?missing subject ID}" ; shift 2 ;;
		-out_path)      OUT_DIR="${2:?missing out dir}"   ; shift 2 ;;
        -species)
			# Normalize input to lower-case, support aliases for macaque
			_species_raw="${2:?missing species}" ; shift 2
			_species_lc="${_species_raw,,}"
			case "$_species_lc" in
				macaque|cynomolgus|rhesus) SPECIES="Macaque" ;;
				chimpanzee)               SPECIES="Chimpanzee" ;;
				marmoset)                 SPECIES="Marmoset" ;;
				*)
					err "Unknown species: ${_species_raw}. Use macaque|cynomolgus|rhesus|chimpanzee|marmoset (case-insensitive)."
					;;
			esac
			;;
		# `primx neuro preprocess-3` forwards the same options to 3-1 and
		# 3-2. Hybrid aseg is created in 3-1, so 3-2 only consumes the flag.
		-hybrid-aseg|-no-hybrid-aseg)
			shift
			;;
		-threads|--threads)
			THREADS="${2:?missing thread count}" ; shift 2
			;;
		-h|--help)      usage ; exit 0                     ;;
		*)              err "Unknown option: $1"           ;;
	esac
done

[[ $THREADS =~ ^[1-9][0-9]*$ ]] || err "-threads must be a positive integer"
log "Thread count: $THREADS"

[[ -z ${SUB_ID:-} ]] && err "Subject ID (-id) is required"
[[ -z ${OUT_DIR:-} ]] && err "Output directory (-out_path) is required"

JOB_DIR="$OUT_DIR"
[[ -d $JOB_DIR ]] || err "Directory $JOB_DIR not found"

# ─────────────────────── env / path setup ────────────────────────────
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
TEMPLATE_DIR="$SCRIPT_DIR/template/$SPECIES"

export SUBJECTS_DIR="$JOB_DIR"       # FS root
FS_SUB_DIR="$SUBJECTS_DIR/$SUB_ID"
FS_MRI_DIR="$FS_SUB_DIR/mri"
FS_SURF="$FS_SUB_DIR/surf"
mkdir -p "$FS_SUB_DIR/touch"

log "SUBJECTS_DIR = $SUBJECTS_DIR"
log "Using templates in $TEMPLATE_DIR"

cd "$JOB_DIR"/tmp || err "Cannot cd to $JOB_DIR/tmp"

# ------------------------------------------------------------------
# 1. WM fill & orig surfaces (nofix)
# ------------------------------------------------------------------
log "[1] Fill WM + create initial orig surfaces"
ASEG="$FS_MRI_DIR/aseg.presurf.mgz"
WM="$FS_MRI_DIR/wm.mgz"
NORM="$FS_MRI_DIR/norm.mgz"
FILL="$FS_MRI_DIR/filled.mgz" # later generated
[[ -f $ASEG ]] || err "aseg.presurf.mgz not found in $FS_MRI_DIR"
[[ -f $WM ]]   || err "wm.mgz not found in $FS_MRI_DIR"
[[ -f $NORM ]] || err "norm.mgz not found in $FS_MRI_DIR"

# 1.1 Fill in WM
# FreeSurfer 7.2/7.4 can abort in the automatic segmentation-assisted CC
# seed path for non-human inputs. Label 253 is the central corpus callosum;
# its centroid provides an anatomically appropriate explicit voxel seed.
# -CV bypasses that automatic seed/cleanup path while retaining
# segmentation-guided filling.
CC_SEED_MASK="$JOB_DIR/tmp/${SUB_ID}.cc_central.seed.nii.gz"
mri_binarize --i "$ASEG" --match 253 --o "$CC_SEED_MASK"
read -r CC_VOXELS _ <<< "$(fslstats "$CC_SEED_MASK" -V)"
[[ $CC_VOXELS =~ ^[0-9]+$ && $CC_VOXELS -gt 0 ]] || \
	err "Cannot derive mri_fill seed: CC label 253 is absent from $ASEG"
read -r CC_C_FLOAT CC_R_FLOAT CC_S_FLOAT <<< "$(fslstats "$CC_SEED_MASK" -C)"
read -r CC_C CC_R CC_S <<< "$(
	awk -v c="$CC_C_FLOAT" -v r="$CC_R_FLOAT" -v s="$CC_S_FLOAT" \
		'BEGIN { printf "%.0f %.0f %.0f\n", c, r, s }'
)"
log "$SPECIES mri_fill CC seed (voxel): $CC_C $CC_R $CC_S"
mri_fill -CV "$CC_C" "$CC_R" "$CC_S" \
	-xform "$FS_MRI_DIR/transforms/talairach.lta" \
	-segmentation "$ASEG" "$WM" "$FILL"

# 1.2 Initial orig surfaces, left 255, right 127
# Left
mri_pretess "$FILL" 255 "$NORM" "$FS_MRI_DIR/filled-pretess255.mgz"
mri_tessellate "$FS_MRI_DIR/filled-pretess255.mgz" 255 "$FS_SURF/lh.orig.nofix"
mris_extract_main_component "$FS_SURF/lh.orig.nofix" "$FS_SURF/lh.orig.nofix"
# Right
mri_pretess "$FILL" 127 "$NORM" "$FS_MRI_DIR/filled-pretess127.mgz"
mri_tessellate "$FS_MRI_DIR/filled-pretess127.mgz" 127 "$FS_SURF/rh.orig.nofix"
mris_extract_main_component "$FS_SURF/rh.orig.nofix" "$FS_SURF/rh.orig.nofix"

# ------------------------------------------------------------------
# 2. Smooth, inflate, qsphere, topology‑fix
# ------------------------------------------------------------------
log "[2] Smooth → inflate → qsphere → topology fix"
for hemi in lh rh; do
	mris_smooth  -nw -seed 1234 "$FS_SURF/${hemi}.orig.nofix" "$FS_SURF/${hemi}.smoothwm.nofix"
	mris_inflate -no-save-sulc "$FS_SURF/${hemi}.smoothwm.nofix" "$FS_SURF/${hemi}.inflated.nofix"
	mris_sphere -threads "$THREADS" -q -seed 1234 \
				"$FS_SURF/${hemi}.inflated.nofix" "$FS_SURF/${hemi}.qsphere.nofix"
	# copy to canonical names
	cp "$FS_SURF/${hemi}.orig.nofix"     "$FS_SURF/${hemi}.orig"
	cp "$FS_SURF/${hemi}.inflated.nofix" "$FS_SURF/${hemi}.inflated"
	# topology fix
	mris_fix_topology -threads "$THREADS" \
						-mgz -sphere qsphere.nofix -ga -seed 1234 "$SUB_ID" "$hemi" \
						-rusage "$FS_SUB_DIR/touch/rusage.mris_fix_topology.${hemi}.dat"
	mris_remove_intersection "$FS_SURF/${hemi}.orig" "$FS_SURF/${hemi}.orig"
	rm -f "$FS_SURF/${hemi}.inflated"  # will regenerate
	mris_euler_number "$FS_SURF/${hemi}.orig"
done

# ------------------------------------------------------------------
# 3. Build white.preaparc, inflate again, curvature
# ------------------------------------------------------------------
log "[3] Build white.preaparc + curvature"
for hemi in lh rh; do
	mris_make_surfaces -openmp "$THREADS" \
						-aseg aseg.presurf -white white.preaparc \
						-noaparc -whiteonly  -mgz -T1 brain.finalsurfs "$SUB_ID" "$hemi"
	mris_smooth -n 3 -nw -seed 1234 "$FS_SURF/${hemi}.white.preaparc" "$FS_SURF/${hemi}.smoothwm"
	mris_inflate -rusage "$FS_SUB_DIR/touch/rusage.mris_inflate.${hemi}.dat" \
				"$FS_SURF/${hemi}.smoothwm" "$FS_SURF/${hemi}.inflated"
	mris_curvature -w "$FS_SURF/${hemi}.white.preaparc"
	mris_curvature -thresh .999 -n -a 5 -w -distances 10 10 "$FS_SURF/${hemi}.inflated"
	mris_curvature_stats -m --writeCurvatureFiles -G \
			-o "$FS_SUB_DIR/stats/${hemi}.curv.stats" -F smoothwm "$SUB_ID" "$hemi" curv sulc
	# sphere for registration
	mris_sphere -threads "$THREADS" -seed 1234 \
				-rusage "$FS_SUB_DIR/touch/rusage.mris_sphere.${hemi}.dat" \
				"$FS_SURF/${hemi}.inflated" "$FS_SURF/${hemi}.sphere"
done

# ------------------------------------------------------------------
# 4. Register to Buckner40 curvature template + Jacobian
# ------------------------------------------------------------------
log "[4] Register spheres to Buckner40 template"

for hemi in lh rh; do
	# register sphere to Buckner40 curvature template
	# Constrain surface registration in FS in Marmoset- by Takuya Hayashi in NHPpipeline
	if [[ $SPECIES == "Marmoset" ]]; then
		dist="-dist 20";
		max_degrees="-max_degrees 50";
		TIF="$TEMPLATE_DIR/${hemi}.average.curvature.2018-01-31.tif"
	else
		dist="";
		max_degrees="";
		TIF="$TEMPLATE_DIR/${hemi}.average.curvature.filled.buckner40.tif"
	fi
	mris_register -threads "$THREADS" -curv $dist $max_degrees \
					"$FS_SURF/${hemi}.sphere" \
				"$TIF" \
				"$FS_SURF/${hemi}.sphere.reg"

	mris_jacobian "$FS_SURF/${hemi}.white.preaparc" "$FS_SURF/${hemi}.sphere.reg" \
					"$FS_SURF/${hemi}.jacobian_white"
	# paint macaque avg curvature (optional)
	mrisp_paint -a 5 "$TIF" \
				"$FS_SURF/${hemi}.sphere.reg" \
				"$FS_SURF/${hemi}.avg_curv"

	# parcellation annotations, can add other template!!!
	mris_ca_label -l "$FS_SUB_DIR/label/${hemi}.cortex.label" -aseg "$ASEG" -seed 1234 \
		"$SUB_ID" "$hemi" "$FS_SURF/${hemi}.sphere.reg" \
		"$FREESURFER_HOME/average/${hemi}.DKaparc.atlas.acfb40.noaparc.i12.2016-08-02.gcs" \
		"$FS_SUB_DIR/label/${hemi}.aparc.annot"
	mris_ca_label -l "$FS_SUB_DIR/label/${hemi}.cortex.label" -aseg "$ASEG" -seed 1234 \
		"$SUB_ID" "$hemi" "$FS_SURF/${hemi}.sphere.reg" \
		"$FREESURFER_HOME/average/${hemi}.destrieux.simple.2009-07-29.gcs" \
		"$FS_SUB_DIR/label/${hemi}.aparc.a2009s.annot"
done

# ------------------------------------------------------------------
# 5. Generate pial & final ribbon / volmask
# ------------------------------------------------------------------
log "[5] Generate pial surfaces & volumetric ribbon masks"

# Marmoset uses a dedicated T1-only workflow because its pial placement is
# particularly sensitive to low-frequency cortical intensity variation. The
# helper keeps final white placement on the unchanged brain.finalsurfs volume,
# then applies N4/mode-0/local-GM refinement only to the Marmoset pial pass.
if [[ $SPECIES == "Marmoset" ]]; then
	MARMOSET_PIAL_HELPER="$SCRIPT_DIR/pyscript/MarmosetPialRefinement.sh"
	[[ -x $MARMOSET_PIAL_HELPER ]] \
		|| err "Marmoset pial helper is missing or not executable: $MARMOSET_PIAL_HELPER"
	"$MARMOSET_PIAL_HELPER" \
		--subject "$SUB_ID" \
		--subjects-dir "$SUBJECTS_DIR" \
		--threads "$THREADS"
else
	# NHPPipelines has a dedicated Macaque profile but no Chimpanzee profile.
	# The Chimpanzee settings scale the Macaque profile from a 2x enlarged
	# workspace to PrimateX's fixed 1.25x enlargement.
	case "$SPECIES" in
		Macaque)
			PIAL_REFINEMENT_ARGS=(
				-variablesigma 10
				-psigma 5
				-max 10
			)
			;;
		Chimpanzee)
			PIAL_REFINEMENT_ARGS=(
				-variablesigma 6
				-psigma 3
				-max 6.25
			)
			;;
	esac

	log "Using $SPECIES pial refinement: ${PIAL_REFINEMENT_ARGS[*]}"
	for hemi in lh rh; do
		mris_make_surfaces -openmp "$THREADS" "${PIAL_REFINEMENT_ARGS[@]}" \
							-orig_white white.preaparc \
							-noaparc -aseg aseg.presurf -filled filled -wm wm \
							-mgz -T1 brain.finalsurfs "$SUB_ID" "$hemi"
	done
fi

# Create cortical ribbon & sample WM / GM intensities
mris_volmask --aseg_name aseg.presurf --label_left_white 2 --label_left_ribbon 3 \
            --label_right_white 41 --label_right_ribbon 42 --save_ribbon "$SUB_ID"

for hemi in lh rh; do
	# WM (at projdist -1), GM (projfrac 0.3)
	mri_vol2surf --mov "$FS_MRI_DIR/rawavg.mgz" --hemi "$hemi" --interp trilinear --regheader "$SUB_ID" \
				--noreshape --projdist -1 --o "$FS_SURF/${hemi}.wm.mgh"
	mri_vol2surf --mov "$FS_MRI_DIR/rawavg.mgz" --hemi "$hemi" --interp trilinear --regheader "$SUB_ID" \
				--noreshape --projfrac 0.3 --o "$FS_SURF/${hemi}.gm.mgh"
done

log "Surface reconstruction finished 🎉"
