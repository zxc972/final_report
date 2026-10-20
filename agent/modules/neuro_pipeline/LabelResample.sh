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
#  LabelResample.sh — Resample Gifti labels to subject Freesurfer .annot format
# -----------------------------------------------------------------------------
#  Major blocks
#  ─────────────
#    1. Parameter parsing & environment setup
#    2. Species-specific configuration
#    3. Path setup and validation
#    4. Hemisphere processing loop
#       a) Label file selection
#       b) Mesh sphere registration verification
#       c) Label resampling to native mesh
#       d) Conversion of resampled labels to .annot format
#       e) Generation of anatomical statistics
#
#  Requirements
#    • FreeSurfer environment (mris_convert, mris_anatomical_stats)
#    • Connectome Workbench (wb_command)
#
#  Usage: ./LabelResample.sh \
#         -id <SUBJECT_ID> \
#         -out_path <OUTPUT_DIR> \
#         -left_label <LEFT_HEMI_LABEL.gii> \
#         -right_label <RIGHT_HEMI_LABEL.gii> \
#         [-output_name Output] [-species Macaque] [-resolution 32] [-msmsulc]
#
#  Notes
#    • -species is currently case-sensitive: Macaque, Chimpanzee, Marmoset.
#    • Use -msmsulc when Freesurfer2CaretandRegister.sh was run with -msmsulc.
#
# -----------------------------------------------------------------------------
#  Author: Yichun Huang <ychunhuang@foxmail.com>
#  Updated: 2025-07-28
# -----------------------------------------------------------------------------

set -euo pipefail

# ───────────────────────── helper functions ──────────────────────────
usage() { grep -E "^#  " "$0" | cut -c4- ; exit 0; }
log()   { printf '\e[1;36m[INFO]  %s\e[0m\n'  "$*"; }
err()   { printf '\e[1;31m[ERROR] %s\e[0m\n' "$*" >&2; exit 1; }

# ───────────────────────── default params ───────────────────────────
RES=32
NAME=Output
SPECIES='Macaque'  # Default species

# ───────────────────────── arg parsing ──────────────────────────────
[[ $# -eq 0 ]] && usage
while [[ $# -gt 0 ]]; do
	case "$1" in
		-id)         SUB_ID="${2:?}";          shift 2 ;;
		-out_path)   OUT_DIR="${2%/}";         shift 2 ;;
        -left_label)  LEFT_LABEL="${2:?}";     shift 2 ;;
        -right_label) RIGHT_LABEL="${2:?}";    shift 2 ;;
        -output_name) NAME="${2:?}";           shift 2 ;;
		-msmsulc)    MSM_SULC=true;            shift ;;
        -species)   SPECIES="${2:?}";          shift 2 ;;
		-resolution) RES="${2}";               shift 2 ;;
		-h|--help)   usage ;;
		*) err "Unknown option $1" ;;
	esac
done
[[ -z ${SUB_ID:-} || -z ${OUT_DIR:-} || -z ${LEFT_LABEL:-} || -z ${RIGHT_LABEL:-} ]] && err "-id and -out_path and -left_label and -right_label are required"
if [[ ! "$LEFT_LABEL" =~ \.gii$ ]] || [[ ! "$RIGHT_LABEL" =~ \.gii$ ]]; then
    err "Both left and right labels must be in .gii format"
fi

# Set species-specific parameters
case "$SPECIES" in
	Macaque)    SURF_ATLAS="standard_mesh_atlases_macaque" ;;
	Chimpanzee) SURF_ATLAS="standard_mesh_atlases_chimp" ;;
	Marmoset)   SURF_ATLAS="standard_mesh_atlases_marmoset" ;;
	*) err "Unknown species: $SPECIES" ;;
esac

# ───────────────────────── path setup ───────────────────────────────
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
TEMPLATE_DIR="$SCRIPT_DIR/template"
SURF_ATLAS="$TEMPLATE_DIR/$SURF_ATLAS"  # Standard mesh atlases

SUBJECTS_DIR="$OUT_DIR/"           # FS subject root
export SUBJECTS_DIR
FS_SUB="$SUBJECTS_DIR/$SUB_ID"

ATLAS_DIR="$FS_SUB/HCP_Style_Dir"
NATIVE_DIR="$ATLAS_DIR/Native"


log "Subject       : $SUB_ID"
log "Output dir    : $OUT_DIR"
log "Resolution    : ${RES}k"
log "Left label    : $LEFT_LABEL"
log "Right label   : $RIGHT_LABEL"

# ───────────────────────── hemi loop ─────────────
for H in L R; do
    hemi=$( [[ $H == L ]] && echo l || echo r )
	STRUCT=$( [[ $H == L ]] && echo CORTEX_LEFT || echo CORTEX_RIGHT )

    if [[ ${H} == L ]]; then
        LABEL="$LEFT_LABEL"
    else
        LABEL="$RIGHT_LABEL"
    fi
    log "   • Hemisphere $STRUCT — native mesh, label: $LABEL"

    if [ "${MSM_SULC:-}" ]; then
        log "   • MSMSulc enabled, using MSMSulc registered sphere"
        OUT_SPH_REG="$NATIVE_DIR/$SUB_ID.$H.sphere.MSMSulc.native.surf.gii"
    else
        log "   • MSMSulc not enabled, using native sphere"
        OUT_SPH_REG="$NATIVE_DIR/$SUB_ID.$H.sphere.reg.reg_LR.native.surf.gii"
    fi

	ATLAS_SPH="$SURF_ATLAS/$H.sphere.${RES}k_fs_LR.surf.gii"

    if [[ ! -f "$OUT_SPH_REG" ]]; then
        err "Sphere registration file not found: $OUT_SPH_REG"
    fi

    # Resample the label to the native mesh
    log "   • Resampling $H hemisphere label to native mesh"
    wb_command -label-resample \
        "$LABEL" \
        "$ATLAS_SPH" \
        "$OUT_SPH_REG" BARYCENTRIC \
        "$NATIVE_DIR/tmp_parcellation.${H}.native.label.gii"

    # Convert the resampled label to .annot format
    log "   • Converting $H hemisphere label to .annot format"
    mris_convert --annot "$NATIVE_DIR/tmp_parcellation.${H}.native.label.gii" \
        "$NATIVE_DIR/$SUB_ID.$H.white.native.surf.gii" \
        "$FS_SUB/label/${hemi}h.${NAME}.annot" \

    mris_anatomical_stats \
        -a "$FS_SUB/label/${hemi}h.${NAME}.annot" \
        -f "$FS_SUB/stats/${hemi}h.${NAME}.stats" \
        "$SUB_ID" "${hemi}h"

done


