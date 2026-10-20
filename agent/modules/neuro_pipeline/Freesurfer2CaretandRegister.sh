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
#  Freesurfer2CaretandRegister.sh —  Convert FreeSurfer surfaces to CARET/WB
#                                     format and register to fs_LR meshes
# -----------------------------------------------------------------------------
#  Major blocks
#  ─────────────
#    1.  Parse arguments & env setup
#    2.  Build subject/atlas folders
#    3.  Generate c_ras affine  (FS voxel ↔ surface)
#    4.  Per‑hemisphere native‑mesh processing
#          a)  convert surfaces → GIFTI; apply affine
#          b)  midthickness, inflated, sphere
#          c)  shapes: sulc / thickness / curvature (invert, palette)
#          d)  ROI, fill holes, remove islands
#          e)  labels (aparc / aparc.a2009s)
#    5.  Resample to 164 k fs_LR & (optionally) LowResMesh (32 k default)
#    6.  Distortion maps & strain
#    7.  Metric / label resample ADAP_BARY_AREA
#    8.  Create CIFTI dscalar / dlabel outputs
#
#  Requirements
#    • FreeSurfer env (mris_*)
#    • Connectome Workbench (wb_command)
#    • FSL (mri_info, bc)
#
#  Usage :  ./Freesurfer2CaretandRegister.sh \
#              -id <SUB> -out_path <DIR> \
#              [-LowResMesh 32] [-InflateExtraScale 1] \
#              [-species|--species <Macaque|Chimpanzee|Marmoset|Cynomolgus|Rhesus>] \
#              [-msmsulc]
#              # NOTE: -species/--species is case-insensitive; Cynomolgus/Rhesus are treated as Macaque
#              # NOTE: -msmsulc requires msm and the bundled MSMConfig files.
#
# -----------------------------------------------------------------------------
#  Author  :  Yichun Huang  <ychunhuang@foxmail.com>
#  Updated :  2025-06-10  (refactor + logging)
#  Reference: NHPpipeline
#  https://github.com/Washington-University/NHPPipelines/blob/master/PostFreeSurfer/scripts/FreeSurfer2CaretConvertAndRegisterNonlinear.sh
# -----------------------------------------------------------------------------
set -euo pipefail

# ───────────────────────── helper fns ───────────────────────────────
usage() { grep -E "^#  " "$0" | cut -c4- ; exit 0 ; }
log()  	{ printf '\e[1;36m[INFO]  %s\e[0m\n'  "$*"; }
warn() 	{ printf '\e[1;33m[WARN]  %s\e[0m\n'  "$*"; }
err()  	{ printf '\e[1;31m[ERROR] %s\e[0m\n' "$*" >&2; exit 1; }

# ───────────────────────── default params ───────────────────────────
LOW_MESH=32
INFLATE_SCALE=1
SPECIES=Macaque

# ───────────────────────── arg parsing ──────────────────────────────
[[ $# -eq 0 ]] && usage
while [[ $# -gt 0 ]]; do
	case "$1" in
		-id)         SUB_ID="${2:?}";          shift 2 ;;
		-out_path)   OUT_DIR="${2%/}";         shift 2 ;;
		-species|--species) SPECIES="${2:?}";  shift 2 ;;
		-msmsulc)    MSM_SULC=true;            shift ;;
		-LowResMesh) LOW_MESH="${2}";          shift 2 ;;
		-InflateExtraScale) INFLATE_SCALE="${2}"; shift 2 ;;
		-h|--help)   usage ;;
		*) err "Unknown option $1" ;;
	esac
done
[[ -z ${SUB_ID:-} || -z ${OUT_DIR:-} ]] && err "-id and -out_path are required"

# Normalize species input (case-insensitive)
# trim leading/trailing whitespace and lowercase
SPECIES="$(printf '%s' "${SPECIES:-}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | tr '[:upper:]' '[:lower:]')"

# Set species-specific parameters (case-insensitive; cynomolgus/rhesus -> macaque)
STANDARD_MESH_AVAILABLE=true
case "$SPECIES" in
	macaque|cynomolgus|rhesus) SURF_ATLAS="standard_mesh_atlases_macaque" ;;
	chimpanzee)               SURF_ATLAS="standard_mesh_atlases_chimp" ;;
	marmoset)
		SURF_ATLAS="standard_mesh_atlases_marmoset"
		STANDARD_MESH_AVAILABLE=false
		;;
	*) err "Unknown species: ${SPECIES}. Supported: Macaque/Chimpanzee/Marmoset/Cynomolgus/Rhesus (case-insensitive)" ;;
esac

# ───────────────────────── path setup ───────────────────────────────
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
TEMPLATE_DIR="$SCRIPT_DIR/template"
MSMCONFIGDIR="$SCRIPT_DIR/MSMConfig"
SURF_ATLAS="$TEMPLATE_DIR/$SURF_ATLAS"  # Standard mesh atlases
HIGH_MESH=164

if [[ "$STANDARD_MESH_AVAILABLE" == true && ! -d "$SURF_ATLAS" ]]; then
	warn "Standard mesh atlas not found: $SURF_ATLAS"
	warn "Proceeding in Native-only mode."
	STANDARD_MESH_AVAILABLE=false
fi

SUBJECTS_DIR="$OUT_DIR/"           # FS subject root
export SUBJECTS_DIR
FS_SUB="$SUBJECTS_DIR/$SUB_ID"
FS_MRI="$FS_SUB/mri"
FS_SURF="$FS_SUB/surf"

ATLAS_DIR="$FS_SUB/HCP_Style_Dir"
NATIVE_DIR="$ATLAS_DIR/Native"
mkdir -p "$ATLAS_DIR"/{fsaverage,fsaverage_LR${LOW_MESH}k} "$NATIVE_DIR"

log "Subject       : $SUB_ID"
log "Output dir    : $OUT_DIR"
log "LowResMesh    : ${LOW_MESH}k"
log "Inflate scale : $INFLATE_SCALE"
if [[ "$STANDARD_MESH_AVAILABLE" != true ]]; then
	warn "Native-only mode: fs_LR/${LOW_MESH}k resampling and CIFTI outputs will be skipped."
fi

# ───────────────────────── affine matrix (c_ras) ────────────────────
log "   • Generate c_ras affine"
cr=$(mri_info "$OUT_DIR/T1.nii.gz" | grep "c_r" | cut -d "=" -f 5 | sed s/" "/""/g)
ca=$(mri_info "$OUT_DIR/T1.nii.gz" | grep "c_a" | cut -d "=" -f 5 | sed s/" "/""/g)
cs=$(mri_info "$OUT_DIR/T1.nii.gz" | grep "c_s" | cut -d "=" -f 5 | sed s/" "/""/g)
cat > "$FS_MRI/c_ras.mat" <<EOF
1 0 0 $cr
0 1 0 $ca
0 0 1 $cs
0 0 0 1
EOF

# ───────────────────────── hemi loop: Native processing ─────────────
for H in L R; do
	hemi=$( [[ $H == L ]] && echo l || echo r )
	STRUCT=$( [[ $H == L ]] && echo CORTEX_LEFT || echo CORTEX_RIGHT )
	log "**********START MAIN NATIVE MESH PROCESSING**********"
	log "   • Hemisphere $STRUCT — native mesh"

	# ---------- convert surfaces (white / pial / smoothwm) ------------
	TYPES="ANATOMICAL@GRAY_WHITE ANATOMICAL@PIAL ANATOMICAL@GRAY_WHITE"
	i=1
	for surf in white pial smoothwm; do
		Type=$(echo "$TYPES" | cut -d " " -f $i)
		Secondary=$(echo "$Type" | cut -d "@" -f 2)
		Type=$(echo "$Type" | cut -d "@" -f 1)
		if [ ! "$Secondary" = "$Type" ]; then
			Secondary=" -surface-secondary-type $Secondary"
		else
			Secondary=""
		fi
		out="$NATIVE_DIR/$SUB_ID.$H.$surf.native.surf.gii"
		mris_convert "$FS_SURF/${hemi}h.$surf" "$out"
		wb_command -set-structure "$out" "$STRUCT" -surface-type ${Type}${Secondary}
		wb_command -surface-apply-affine "$out" "$FS_MRI/c_ras.mat" "$out"
		i=$((i + 1))
	done

	# ---------- midthickness & inflated ------------------------------
	# Create midthickness by averaging smoothwm?(white???) and pial surfaces and use it to make inflated surfacess
	log "   • Create midthickness and inflated surfaces"
	wb_command -surface-average "$NATIVE_DIR/$SUB_ID.$H.midthickness.native.surf.gii" \
		-surf "$NATIVE_DIR/$SUB_ID.$H.white.native.surf.gii" \
		-surf "$NATIVE_DIR/$SUB_ID.$H.pial.native.surf.gii"
	wb_command -set-structure "$NATIVE_DIR/$SUB_ID.$H.midthickness.native.surf.gii" "$STRUCT" -surface-type ANATOMICAL -surface-secondary-type MIDTHICKNESS

	# get number of vertices from native file
	vtx=$(wb_command -file-information "$NATIVE_DIR/$SUB_ID.$H.midthickness.native.surf.gii" | grep 'Number of Vertices:' | cut -f2 -d: | tr -d '[:space:]')

	# HCP fsaverage_LR32k used -iterations-scale 0.75. Compute new param value for native mesh density
	scale=$(echo "scale=4; $INFLATE_SCALE * 0.75 * $vtx / 32492" | bc -l)
	wb_command -surface-generate-inflated "$NATIVE_DIR/$SUB_ID.$H.midthickness.native.surf.gii" \
		"$NATIVE_DIR/$SUB_ID.$H.inflated.native.surf.gii" \
		"$NATIVE_DIR/$SUB_ID.$H.very_inflated.native.surf.gii" -iterations-scale "$scale"

	# ---------- spheres ---------------------------------------------
	log "   • Convert spherical surfaces to gii"
	for s in sphere sphere.reg; do
		o="$NATIVE_DIR/$SUB_ID.$H.$s.native.surf.gii"
		mris_convert "$FS_SURF/${hemi}h.$s" "$o"
		wb_command -set-structure "$o" "$STRUCT" -surface-type SPHERICAL
	done

	# ---------- shapes (sulc, thickness, curvature) ------------------
	log "   • Convert surface data to gii shapes"
	for Map in sulc@sulc@Sulc thickness@thickness@Thickness curv@curvature@Curvature; do
		fsname=$(echo $Map | cut -d "@" -f 1)
		wbname=$(echo $Map | cut -d "@" -f 2)
		mapname=$(echo $Map | cut -d "@" -f 3)

		out="$NATIVE_DIR/$SUB_ID.$H.$wbname.native.shape.gii"
		mris_convert -c "$FS_SURF/${hemi}h.$fsname" "$FS_SURF/${hemi}h.white" "$out"
		wb_command -set-structure "$out" "$STRUCT"
		wb_command -metric-math "var * -1" "$out" -var var "$out"
		wb_command -set-map-names "$out" -map 1 "$SUB_ID"_"$H"_"$mapname"
		wb_command -metric-palette "$out" MODE_AUTO_SCALE_PERCENTAGE -pos-percent 2 98 \
					-palette-name Gray_Interp -disp-pos true -disp-neg true -disp-zero true
	done

	# ---------- ROI from thickness >0, fill holes --------------------
	log "   • Thickness specific operations"
	native_thickness="$NATIVE_DIR/$SUB_ID.$H.thickness.native.shape.gii"
	wb_command -metric-math "abs(th)" "$native_thickness" -var th "$native_thickness"
	wb_command -metric-palette "$native_thickness" MODE_AUTO_SCALE_PERCENTAGE -pos-percent 4 96 \
				-interpolate true -palette-name videen_style -disp-pos true -disp-neg false -disp-zero false
	wb_command -metric-math "th > 0" "$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii" -var th "$native_thickness"
	wb_command -metric-fill-holes "$NATIVE_DIR/$SUB_ID.$H.midthickness.native.surf.gii" \
				"$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii" "$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii"
	wb_command -metric-remove-islands "$NATIVE_DIR/$SUB_ID.$H.midthickness.native.surf.gii" \
				"$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii" "$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii"
	wb_command -set-map-names "$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii" -map 1 "${SUB_ID}_${H}_ROI"
	wb_command -metric-dilate "${native_thickness}" "$NATIVE_DIR/$SUB_ID.$H.midthickness.native.surf.gii" 10 \
				"${native_thickness}" -nearest
	wb_command -metric-dilate "$NATIVE_DIR/$SUB_ID.$H.curvature.native.shape.gii" "$NATIVE_DIR/$SUB_ID.$H.midthickness.native.surf.gii" 10 \
				"$NATIVE_DIR/$SUB_ID.$H.curvature.native.shape.gii" -nearest

	# ---------- label conversion ------------------------------------
	for lbl in aparc aparc.a2009s; do #Remove BA because it doesn't convert properly
		src="$FS_SUB/label/${hemi}h.$lbl.annot"
		[[ -f $src ]] || continue
		out="$NATIVE_DIR/$SUB_ID.$H.$lbl.native.label.gii"
		mris_convert --annot "$src" "$FS_SURF/${hemi}h.white" "$out"
		wb_command -set-structure "$out" "$STRUCT"
		wb_command -set-map-names "$out" -map 1 "${SUB_ID}_${H}_${lbl}"
		wb_command -gifti-label-add-prefix "$out" "${H}_" "$out"
	done

	log "**********END MAIN NATIVE MESH PROCESSING**********"
	log "-----------------------------------------------------"
	log "+"
	log "+"
	log "+"
	log "-----------------------------------------------------"

	if [[ "$STANDARD_MESH_AVAILABLE" != true ]]; then
		log "   • Hemisphere $STRUCT native outputs complete"
		log "   • Skipping fs_LR registration/resampling for this species"
		continue
	fi

	# ---------- FS→fs_LR registration & distortion -------------------
	log "**********START HIRES MESH RESAMPLE**********"
	log "   • FS→fs_LR registration (164k)"
	# Important sphere files
	SRC_SPH="$NATIVE_DIR/$SUB_ID.$H.sphere.reg.native.surf.gii"
	REG_SPH="$NATIVE_DIR/$SUB_ID.$H.sphere.reg.reg_LR.native.surf.gii" # "FS --> FS_LR" registration

	# Copy Atlas Files
	log "   • Copy atlas files (164k)"
	# define
	ATLAS_SPH_FS="$ATLAS_DIR/fsaverage/$SUB_ID.$H.sphere.${HIGH_MESH}k_fs_$H.surf.gii"
	ATLAS_DEF_SPH="$ATLAS_DIR/fsaverage/$SUB_ID.$H.def_sphere.${HIGH_MESH}k_fs_$H.surf.gii"
	ATLAS_HI_SPH="$ATLAS_DIR/$SUB_ID.$H.sphere.${HIGH_MESH}k_fs_LR.surf.gii"
	ATLAS_ROI="$ATLAS_DIR/$SUB_ID.$H.atlasroi.${HIGH_MESH}k_fs_LR.shape.gii"
	REF_SULC="$ATLAS_DIR/$SUB_ID.$H.refsulc.${HIGH_MESH}k_fs_LR.shape.gii" # Used as reference
	# copy
	cp "$SURF_ATLAS/fs_$H/fsaverage.$H.sphere.${HIGH_MESH}k_fs_$H.surf.gii" "$ATLAS_SPH_FS"
	cp "$SURF_ATLAS/fs_$H/fs_$H-to-fs_LR_fsaverage.${H}_LR.spherical_std.${HIGH_MESH}k_fs_$H.surf.gii" "$ATLAS_DEF_SPH"
	cp "$SURF_ATLAS/fsaverage.${H}_LR.spherical_std.${HIGH_MESH}k_fs_LR.surf.gii" "$ATLAS_HI_SPH"
	cp "$SURF_ATLAS/$H.atlasroi.${HIGH_MESH}k_fs_LR.shape.gii" "$ATLAS_ROI"
	cp "$SURF_ATLAS/$H.refsulc.${HIGH_MESH}k_fs_LR.shape.gii" "$REF_SULC"
	if [ -e "$SURF_ATLAS/colin.cerebral.$H.flat.${HIGH_MESH}k_fs_LR.surf.gii" ]; then
		cp "$SURF_ATLAS/colin.cerebral.$H.flat.${HIGH_MESH}k_fs_LR.surf.gii" \
			"$ATLAS_DIR/$SUB_ID.$H.flat.${HIGH_MESH}k_fs_LR.surf.gii"
	fi

	# Concatenate "FS" registration to "FS --> FS_LR" registration
	log "   • fs_LR registration (164k)"
	wb_command -surface-sphere-project-unproject \
		"$SRC_SPH" \
		"$ATLAS_SPH_FS" \
		"$ATLAS_DEF_SPH" \
		"$REG_SPH" # Registered sphere

	# Distortion metrics (areal, edge, strain)
	log "   • Distortion metrics (Areal, Edge, Strain)"
	# areal distortion
	wb_command -surface-vertex-areas "$NATIVE_DIR/$SUB_ID.$H.sphere.native.surf.gii" \
				"$NATIVE_DIR/$SUB_ID.$H.sphere.native.shape.gii"
	wb_command -surface-vertex-areas "$REG_SPH" \
				"$NATIVE_DIR/$SUB_ID.$H.sphere.reg.reg_LR.native.shape.gii"
	wb_command -metric-math "ln(spherereg / sphere) / ln(2)" "$NATIVE_DIR/$SUB_ID.$H.ArealDistortion_FS.native.shape.gii" \
				-var sphere "$NATIVE_DIR/$SUB_ID.$H.sphere.native.shape.gii" \
				-var spherereg "$NATIVE_DIR/$SUB_ID.$H.sphere.reg.reg_LR.native.shape.gii"
	rm "$NATIVE_DIR/$SUB_ID.$H.sphere.native.shape.gii" "$NATIVE_DIR/$SUB_ID.$H.sphere.reg.reg_LR.native.shape.gii"
	wb_command -set-map-names "$NATIVE_DIR/$SUB_ID.$H.ArealDistortion_FS.native.shape.gii" -map 1 "${SUB_ID}_${H}_ArealDistortion_FS"
	wb_command -metric-palette "$NATIVE_DIR/$SUB_ID.$H.ArealDistortion_FS.native.shape.gii" \
				MODE_AUTO_SCALE -palette-name ROY-BIG-BL -thresholding THRESHOLD_TYPE_NORMAL THRESHOLD_TEST_SHOW_OUTSIDE -1 1
	# edge distortion
	wb_command -surface-distortion \
		"$NATIVE_DIR/$SUB_ID.$H.sphere.native.surf.gii" \
		"$REG_SPH" \
		"$NATIVE_DIR/$SUB_ID.$H.EdgeDistortion_FS.native.shape.gii" -edge-method
	# strain diistortion
	wb_command -surface-distortion \
		"$NATIVE_DIR/$SUB_ID.$H.sphere.native.surf.gii" \
		"$REG_SPH" \
		"$NATIVE_DIR/$SUB_ID.$H.Strain_FS.native.shape.gii" -local-affine-method
	wb_command -metric-merge "$NATIVE_DIR/$SUB_ID.$H.StrainJ_FS.native.shape.gii" \
		-metric "$NATIVE_DIR/$SUB_ID.$H.Strain_FS.native.shape.gii" -column 1
	wb_command -metric-merge "$NATIVE_DIR/$SUB_ID.$H.StrainR_FS.native.shape.gii" \
		-metric "$NATIVE_DIR/$SUB_ID.$H.Strain_FS.native.shape.gii" -column 2
	wb_command -metric-math "ln(v) / ln(2)" "$NATIVE_DIR/$SUB_ID.$H.StrainJ_FS.native.shape.gii" \
				-var v "$NATIVE_DIR/$SUB_ID.$H.StrainJ_FS.native.shape.gii"
	wb_command -metric-math "ln(v) / ln(2)" "$NATIVE_DIR/$SUB_ID.$H.StrainR_FS.native.shape.gii" \
				-var v "$NATIVE_DIR/$SUB_ID.$H.StrainR_FS.native.shape.gii"
	rm "$NATIVE_DIR/$SUB_ID.$H.Strain_FS.native.shape.gii"

	# TODO: run MSMSulc registrantion to FS_LR initialized with FS affine
	if [ "${MSM_SULC:-}" ]; then
		log "   • MSMSulc registration (if enabled)"
		# Calculate FS Affine Transform and Apply
		mkdir -p "$NATIVE_DIR/MSMSulc"
		wb_command -surface-affine-regression \
			"$NATIVE_DIR/$SUB_ID.$H.sphere.native.surf.gii" \
			"$NATIVE_DIR/$SUB_ID.$H.sphere.reg.reg_LR.native.surf.gii" \
			"$NATIVE_DIR/MSMSulc/$H.mat"
		wb_command -surface-apply-affine \
			"$NATIVE_DIR/$SUB_ID.$H.sphere.native.surf.gii" \
			"$NATIVE_DIR/MSMSulc/$H.mat" \
			"$NATIVE_DIR/MSMSulc/$H.sphere_rot.surf.gii"
		wb_command -surface-modify-sphere \
			"$NATIVE_DIR/MSMSulc/$H.sphere_rot.surf.gii" 100 "$NATIVE_DIR/MSMSulc/$H.sphere_rot.surf.gii"
		cp "$NATIVE_DIR/MSMSulc/$H.sphere_rot.surf.gii" "$NATIVE_DIR/$SUB_ID.$H.sphere.rot.native.surf.gii"
		# Register using MSMSulc
		DIR=$(pwd)
		cd "$NATIVE_DIR/MSMSulc"
		msm --conf=${MSMCONFIGDIR}/MSMSulcStrainFinalconf \
			--inmesh="$NATIVE_DIR/$SUB_ID.$H.sphere.rot.native.surf.gii" \
			--refmesh="$ATLAS_HI_SPH" \
			--indata="$NATIVE_DIR/$SUB_ID.$H.sulc.native.shape.gii" \
			--refdata="$REF_SULC" \
			--out="$NATIVE_DIR/MSMSulc/$H." --verbose
		cp ${MSMCONFIGDIR}/MSMSulcStrainFinalconf "$NATIVE_DIR/MSMSulc/$H.conf"
		cd $DIR
		cp "$NATIVE_DIR/MSMSulc/$H.sphere.reg.surf.gii" "$NATIVE_DIR/$SUB_ID.$H.sphere.MSMSulc.native.surf.gii"
		wb_command -set-structure "$NATIVE_DIR/$SUB_ID.$H.sphere.MSMSulc.native.surf.gii" "$STRUCT"
		REG_SPH="$NATIVE_DIR/$SUB_ID.$H.sphere.MSMSulc.native.surf.gii" # MSMSulc registered sphere
		# Make MSMSulc Registration Areal Distortion Maps
		wb_command -surface-vertex-areas "$REG_SPH" \
			"$NATIVE_DIR/$SUB_ID.$H.sphere.reg.MSMSulc.native.shape.gii"
		wb_command -surface-vertex-areas "$NATIVE_DIR/$SUB_ID.$H.sphere.native.surf.gii" \
			"$NATIVE_DIR/$SUB_ID.$H.sphere.native.shape.gii"
		wb_command -metric-math "ln(spherereg / sphere) / ln(2)" "$NATIVE_DIR/$SUB_ID.$H.ArealDistortion_MSMSulc.native.shape.gii" \
					-var sphere "$NATIVE_DIR/$SUB_ID.$H.sphere.native.shape.gii" \
					-var spherereg "$NATIVE_DIR/$SUB_ID.$H.sphere.reg.MSMSulc.native.shape.gii"
		rm "$NATIVE_DIR/$SUB_ID.$H.sphere.native.shape.gii" "$NATIVE_DIR/$SUB_ID.$H.sphere.reg.MSMSulc.native.shape.gii"
		wb_command -set-map-names "$NATIVE_DIR/$SUB_ID.$H.ArealDistortion_MSMSulc.native.shape.gii" -map 1 "${SUB_ID}_${H}_ArealDistortion_MSMSulc"
		wb_command -metric-palette "$NATIVE_DIR/$SUB_ID.$H.ArealDistortion_MSMSulc.native.shape.gii" \
					MODE_AUTO_SCALE -palette-name ROY-BIG-BL -thresholding THRESHOLD_TYPE_NORMAL THRESHOLD_TEST_SHOW_OUTSIDE -1 1
		# edge distortion
		wb_command -surface-distortion \
			"$NATIVE_DIR/$SUB_ID.$H.sphere.native.surf.gii" \
			"$REG_SPH" \
			"$NATIVE_DIR/$SUB_ID.$H.EdgeDistortion_MSMSulc.native.shape.gii" -edge-method
		# strain diistortion
		wb_command -surface-distortion \
			"$NATIVE_DIR/$SUB_ID.$H.sphere.native.surf.gii" \
			"$REG_SPH" \
			"$NATIVE_DIR/$SUB_ID.$H.Strain_MSMSulc.native.shape.gii" -local-affine-method
		wb_command -metric-merge "$NATIVE_DIR/$SUB_ID.$H.StrainJ_MSMSulc.native.shape.gii" \
					-metric "$NATIVE_DIR/$SUB_ID.$H.Strain_MSMSulc.native.shape.gii" -column 1
		wb_command -metric-merge "$NATIVE_DIR/$SUB_ID.$H.StrainR_MSMSulc.native.shape.gii" \
					-metric "$NATIVE_DIR/$SUB_ID.$H.Strain_MSMSulc.native.shape.gii" -column 2
		wb_command -metric-math "ln(v) / ln(2)" "$NATIVE_DIR/$SUB_ID.$H.StrainJ_MSMSulc.native.shape.gii" \
					-var v "$NATIVE_DIR/$SUB_ID.$H.StrainJ_MSMSulc.native.shape.gii"
		wb_command -metric-math "ln(v) / ln(2)" "$NATIVE_DIR/$SUB_ID.$H.StrainR_MSMSulc.native.shape.gii" \
					-var v "$NATIVE_DIR/$SUB_ID.$H.StrainR_MSMSulc.native.shape.gii"
		rm "$NATIVE_DIR/$SUB_ID.$H.Strain_MSMSulc.native.shape.gii"
	fi

	# ---------- resample to HighResMesh (164k) ------------------------
	log "   • Resample surfaces/metrics to ${HIGH_MESH}k"
	ROI_HI="${ATLAS_DIR}/${SUB_ID}.$H.atlasroi.${HIGH_MESH}k_fs_LR.shape.gii"
	MID_NATIVE="${NATIVE_DIR}/${SUB_ID}.$H.midthickness.native.surf.gii"
	MID_HI="${ATLAS_DIR}/${SUB_ID}.$H.midthickness.${HIGH_MESH}k_fs_LR.surf.gii"

	log "   • Ensure medial wall ROI"
	# Ensure both individual and atlas medial wall ROI
	wb_command -metric-resample \
		"$ROI_HI" \
		"$ATLAS_HI_SPH" \
		"$REG_SPH" BARYCENTRIC \
		"$NATIVE_DIR/$SUB_ID.$H.atlasroi.native.shape.gii" -largest
	wb_command -metric-math "(atlas + individual) > 0" "$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii" \
		-var atlas "$NATIVE_DIR/$SUB_ID.$H.atlasroi.native.shape.gii" \
		-var individual "$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii"
	wb_command -metric-mask "$native_thickness" \
		"$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii" \
		"$native_thickness"
	wb_command -metric-mask "$NATIVE_DIR/$SUB_ID.$H.curvature.native.shape.gii" \
		"$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii" \
		"$NATIVE_DIR/$SUB_ID.$H.curvature.native.shape.gii"
	
	log "   • Resample surfaces to ${HIGH_MESH}k"
	# Populate Highres fs_LR spec file.  
	# Deform surfaces and other data according to native to folding-based registration selected above.  
	# Regenerate inflated surfaces.
	for surf in white midthickness pial smoothwm; do
		wb_command -surface-resample \
			"$NATIVE_DIR/$SUB_ID.$H.$surf.native.surf.gii" \
			"$REG_SPH" \
			"$ATLAS_HI_SPH" BARYCENTRIC \
			"$ATLAS_DIR/$SUB_ID.$H.$surf.${HIGH_MESH}k_fs_LR.surf.gii"
	done
	# HCP fsaverage_LR32k used -iterations-scale 0.75. Compute new param value for high res mesh density
	infl_scale=$(echo "scale=4; $INFLATE_SCALE * 0.75 * $HIGH_MESH / 32" | bc -l)
	wb_command -surface-generate-inflated "$MID_HI" \
		"$ATLAS_DIR/$SUB_ID.$H.inflated.${HIGH_MESH}k_fs_LR.surf.gii" \
		"$ATLAS_DIR/$SUB_ID.$H.very_inflated.${HIGH_MESH}k_fs_LR.surf.gii" -iterations-scale "$infl_scale"

	# Resample thickness curvature and sulc
	log "   • Resample metric shape files (sulc, thickness, curvature)"
	for m in thickness curvature sulc ; do
		wb_command -metric-resample \
			"$NATIVE_DIR/$SUB_ID.$H.$m.native.shape.gii" \
			"$REG_SPH" \
			"$ATLAS_HI_SPH" ADAP_BARY_AREA \
			"$ATLAS_DIR/$SUB_ID.$H.$m.${HIGH_MESH}k_fs_LR.shape.gii" \
			-area-surfs "$MID_NATIVE" "$MID_HI" \
			-current-roi "$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii"
		wb_command -metric-mask \
			"$ATLAS_DIR/$SUB_ID.$H.$m.${HIGH_MESH}k_fs_LR.shape.gii" \
			"$ROI_HI" \
			"$ATLAS_DIR/$SUB_ID.$H.$m.${HIGH_MESH}k_fs_LR.shape.gii"
	done

	# Distortion maps resample (loop list)
	for m in ArealDistortion_FS EdgeDistortion_FS StrainJ_FS StrainR_FS; do
		wb_command -metric-resample \
			"$NATIVE_DIR/$SUB_ID.$H.$m.native.shape.gii" \
			"$REG_SPH" "$ATLAS_HI_SPH" ADAP_BARY_AREA \
			"$ATLAS_DIR/$SUB_ID.$H.$m.${HIGH_MESH}k_fs_LR.shape.gii" \
			-area-surfs "$MID_NATIVE" "$MID_HI"
	done
	if [ "${MSM_SULC:-}" ]; then
		log "   • MSMSulc distortion maps resample"
		for m in ArealDistortion_MSMSulc EdgeDistortion_MSMSulc StrainJ_MSMSulc StrainR_MSMSulc; do
			wb_command -metric-resample \
				"$NATIVE_DIR/$SUB_ID.$H.$m.native.shape.gii" \
				"$REG_SPH" "$ATLAS_HI_SPH" ADAP_BARY_AREA \
				"$ATLAS_DIR/$SUB_ID.$H.$m.${HIGH_MESH}k_fs_LR.shape.gii" \
				-area-surfs "$MID_NATIVE" "$MID_HI"
		done
	fi

	# Labels resample
	for lbl in aparc aparc.a2009s; do
		[[ -f $NATIVE_DIR/$SUB_ID.$H.$lbl.native.label.gii ]] || continue
		wb_command -label-resample \
			"$NATIVE_DIR/$SUB_ID.$H.$lbl.native.label.gii" \
			"$REG_SPH" \
			"$ATLAS_HI_SPH" BARYCENTRIC \
			"$ATLAS_DIR/$SUB_ID.$H.$lbl.${HIGH_MESH}k_fs_LR.label.gii" -largest
	done
	log "**********END 164k RESAMPLE**********"
	log "-----------------------------------------------------"
	log "+"
	log "+"
	log "+"
	log "-----------------------------------------------------"

	# ---------- LowResMesh resample (if LOW_MESH < HIGH_MESH) ---------
	# Copy atlas files
	log "   • Resample to ${LOW_MESH}k"
	LOW_DIR="$ATLAS_DIR/fsaverage_LR${LOW_MESH}k"
	LOW_SPH="$LOW_DIR/$SUB_ID.$H.sphere.${LOW_MESH}k_fs_LR.surf.gii"
	ROI_LOW="$LOW_DIR/$SUB_ID.$H.atlasroi.${LOW_MESH}k_fs_LR.shape.gii"
	cp "$SURF_ATLAS/$H.sphere.${LOW_MESH}k_fs_LR.surf.gii" "$LOW_SPH"
	cp "$SURF_ATLAS/$H.atlasroi.${LOW_MESH}k_fs_LR.shape.gii" "$ROI_LOW"
	for surf in white midthickness pial smoothwm; do
		wb_command -surface-resample \
			"$NATIVE_DIR/$SUB_ID.$H.$surf.native.surf.gii" \
			"$REG_SPH" \
			"$LOW_SPH" BARYCENTRIC \
			"$LOW_DIR/$SUB_ID.$H.$surf.${LOW_MESH}k_fs_LR.surf.gii"
	done
	# HCP fsaverage_LR32k used -iterations-scale 0.75. Recalculate in case using a different mesh
	infl_scale_low=$(echo "scale=4; $INFLATE_SCALE * 0.75 * $LOW_MESH / 32" | bc -l)
	wb_command -surface-generate-inflated "$LOW_DIR/$SUB_ID.$H.midthickness.${LOW_MESH}k_fs_LR.surf.gii" \
			"$LOW_DIR/$SUB_ID.$H.inflated.${LOW_MESH}k_fs_LR.surf.gii" \
			"$LOW_DIR/$SUB_ID.$H.very_inflated.${LOW_MESH}k_fs_LR.surf.gii" -iterations-scale "$infl_scale_low"
	
	log "   • Resample metric shape files (sulc, thickness, curvature)"
	for m in thickness curvature sulc; do
		wb_command -metric-resample \
			"$NATIVE_DIR/$SUB_ID.$H.$m.native.shape.gii" \
			"$REG_SPH" \
			"$LOW_SPH" ADAP_BARY_AREA \
			"$LOW_DIR/$SUB_ID.$H.$m.${LOW_MESH}k_fs_LR.shape.gii" \
			-area-surfs "$MID_NATIVE" "$LOW_DIR/$SUB_ID.$H.midthickness.${LOW_MESH}k_fs_LR.surf.gii" \
			-current-roi "$NATIVE_DIR/$SUB_ID.$H.roi.native.shape.gii"
		wb_command -metric-mask "$LOW_DIR/$SUB_ID.$H.$m.${LOW_MESH}k_fs_LR.shape.gii" \
			"$ROI_LOW" \
			"$LOW_DIR/$SUB_ID.$H.$m.${LOW_MESH}k_fs_LR.shape.gii"
	done

	# Distortion maps resample (loop list)
	for m in ArealDistortion_FS EdgeDistortion_FS StrainJ_FS StrainR_FS; do
		wb_command -metric-resample \
			"$NATIVE_DIR/$SUB_ID.$H.$m.native.shape.gii" \
			"$REG_SPH" \
			"$LOW_SPH" ADAP_BARY_AREA \
			"$LOW_DIR/$SUB_ID.$H.$m.${LOW_MESH}k_fs_LR.shape.gii" \
			-area-surfs "$MID_NATIVE" "$LOW_DIR/$SUB_ID.$H.midthickness.${LOW_MESH}k_fs_LR.surf.gii"
	done
	if [ "${MSM_SULC:-}" ]; then
		log "   • MSMSulc distortion maps resample"
		for m in ArealDistortion_MSMSulc EdgeDistortion_MSMSulc StrainJ_MSMSulc StrainR_MSMSulc; do
			wb_command -metric-resample \
				"$NATIVE_DIR/$SUB_ID.$H.$m.native.shape.gii" \
				"$REG_SPH" \
				"$LOW_SPH" ADAP_BARY_AREA \
				"$LOW_DIR/$SUB_ID.$H.$m.${LOW_MESH}k_fs_LR.shape.gii" \
				-area-surfs "$MID_NATIVE" "$LOW_DIR/$SUB_ID.$H.midthickness.${LOW_MESH}k_fs_LR.surf.gii"
		done
	fi

	# Labels resample
	for lbl in aparc aparc.a2009s; do
		[[ -f $NATIVE_DIR/$SUB_ID.$H.$lbl.native.label.gii ]] || continue
		wb_command -label-resample \
			"$NATIVE_DIR/$SUB_ID.$H.$lbl.native.label.gii" \
			"$REG_SPH" \
			"$LOW_SPH" BARYCENTRIC \
			"$LOW_DIR/$SUB_ID.$H.$lbl.${LOW_MESH}k_fs_LR.label.gii" -largest
	done
	log "**********END ${LOW_MESH} k RESAMPLE**********"
	log "   • Hemisphere $STRUCT done"
done

if [[ "$STANDARD_MESH_AVAILABLE" != true ]]; then
	log "Native GIFTI conversion completed ✔"
	log "No species standard mesh was used; fs_LR/${LOW_MESH}k and CIFTI outputs were not generated."
	exit 0
fi

# ───────────────────────── create CIFTI maps (LowResMesh) ───────────
log "[3] Create CIFTI dscalar/dlabel at ${LOW_MESH}k"
LOW_DIR="$ATLAS_DIR/fsaverage_LR${LOW_MESH}k"
MESH="${LOW_MESH}k_fs_LR"
ROI="atlasroi"
create_dscalar() {
	local name=$1; shift; wb_command -cifti-create-dense-scalar "$LOW_DIR/$SUB_ID.$name.$MESH.dscalar.nii" "$@" ; }

create_dscalar sulc -left-metric "$LOW_DIR/$SUB_ID.L.sulc.$MESH.shape.gii"  \
			-right-metric "$LOW_DIR/$SUB_ID.R.sulc.$MESH.shape.gii"
wb_command -set-map-names "$LOW_DIR/$SUB_ID.sulc.$MESH.dscalar.nii" -map 1 "${SUB_ID}_Sulc"
wb_command -cifti-palette "$LOW_DIR/$SUB_ID.sulc.$MESH.dscalar.nii" MODE_AUTO_SCALE_PERCENTAGE "$LOW_DIR/$SUB_ID.sulc.$MESH.dscalar.nii" \
			-pos-percent 2 98 -palette-name Gray_Interp -disp-pos true -disp-neg true -disp-zero true

create_dscalar curvature -left-metric "$LOW_DIR/$SUB_ID.L.curvature.$MESH.shape.gii" -roi-left "$LOW_DIR/$SUB_ID.L.$ROI.$MESH.shape.gii" \
            -right-metric "$LOW_DIR/$SUB_ID.R.curvature.$MESH.shape.gii" -roi-right "$LOW_DIR/$SUB_ID.R.$ROI.$MESH.shape.gii"
wb_command -set-map-names "$LOW_DIR/$SUB_ID.curvature.$MESH.dscalar.nii" -map 1 "${SUB_ID}_Curvature"
wb_command -cifti-palette "$LOW_DIR/$SUB_ID.curvature.$MESH.dscalar.nii" MODE_AUTO_SCALE_PERCENTAGE "$LOW_DIR/$SUB_ID.curvature.$MESH.dscalar.nii" \
			-pos-percent 2 98 -palette-name Gray_Interp -disp-pos true -disp-neg true -disp-zero true

create_dscalar thickness   -left-metric "$LOW_DIR/$SUB_ID.L.thickness.$MESH.shape.gii" -roi-left "$LOW_DIR/$SUB_ID.L.$ROI.$MESH.shape.gii" \
            -right-metric "$LOW_DIR/$SUB_ID.R.thickness.$MESH.shape.gii" -roi-right "$LOW_DIR/$SUB_ID.R.$ROI.$MESH.shape.gii"
wb_command -set-map-names "$LOW_DIR/$SUB_ID.thickness.$MESH.dscalar.nii" -map 1 "${SUB_ID}_Thickness"
wb_command -cifti-palette "$LOW_DIR/$SUB_ID.thickness.$MESH.dscalar.nii" MODE_AUTO_SCALE_PERCENTAGE "$LOW_DIR/$SUB_ID.thickness.$MESH.dscalar.nii" \
			-pos-percent 4 96 -palette-name videen_style -disp-pos true -disp-neg false -disp-zero false

create_dscalar ArealDistortion_FS -left-metric "$LOW_DIR/$SUB_ID.L.ArealDistortion_FS.$MESH.shape.gii" \
			-right-metric "$LOW_DIR/$SUB_ID.R.ArealDistortion_FS.$MESH.shape.gii"
wb_command -set-map-names "$LOW_DIR/$SUB_ID.ArealDistortion_FS.$MESH.dscalar.nii" -map 1 "${SUB_ID}_ArealDistortion_FS"
wb_command -cifti-palette "$LOW_DIR/$SUB_ID.ArealDistortion_FS.$MESH.dscalar.nii" MODE_USER_SCALE "$LOW_DIR/$SUB_ID.ArealDistortion_FS.$MESH.dscalar.nii" \
			-pos-user 0 1 -neg-user 0 -1 -palette-name ROY-BIG-BL -disp-pos true -disp-neg true -disp-zero false

for lbl in aparc aparc.a2009s; do
	[[ -f $LOW_DIR/$SUB_ID.L.$lbl.$MESH.label.gii ]] || continue
	wb_command -cifti-create-label "$LOW_DIR/$SUB_ID.$lbl.$MESH.dlabel.nii" \
		-left-label "$LOW_DIR/$SUB_ID.L.$lbl.$MESH.label.gii"  -roi-left "$LOW_DIR/$SUB_ID.L.$ROI.$MESH.shape.gii" \
		-right-label "$LOW_DIR/$SUB_ID.R.$lbl.$MESH.label.gii" -roi-right "$LOW_DIR/$SUB_ID.R.$ROI.$MESH.shape.gii"
	wb_command -set-map-names "$LOW_DIR/$SUB_ID.$lbl.$MESH.dlabel.nii" -map 1 "${SUB_ID}_$lbl"
done

log "Pipeline completed ✔"
