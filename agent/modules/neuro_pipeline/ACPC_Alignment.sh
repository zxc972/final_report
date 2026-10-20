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
#  ACPC_Alignment.sh
# -----------------------------------------------------------------------------
#  Purpose  : Align T1 image to species-specific AC-PC reference space.
#             Must be run **after** skull-strip (brain_mask) and before
#             WM segmentation.
#
#  Workflow :
#      1. Field-of-view (FOV) crop with FSL robustfov.
#      2. 6-DOF rigid FLIRT to a species-specific reference (or user-provided).
#      3. Combine transforms → single rigid matrix (acpc.mat).
#      4. Apply to T1 + brain_mask (and optional WM mask).
#
#  Usage    :
#      ./ACPC_Alignment.sh -out_path <DIR> [-brainSize <mm>] \
#                          [-species <SPECIES> | -reference <TEMPLATE>] \
#                          [-with_wm] [-h]
#
#  Required :
#      -out_path     Folder that already contains:
#                       T1.nii.gz            (raw T1)
#                       brain_mask.nii.gz    (binary mask)
#
#  Options  :
#      -brainSize    RobustFOV brain radius (mm) [100]; typical values:
#                    macaque ~80-100, marmoset ~60, chimpanzee ~150
#      -species      Species for built-in template:
#                    macaque|cynomolgus|rhesus, chimpanzee, marmoset
#                    (case-insensitive; overrides -reference if both are set)
#      -reference    Custom template brain path for FLIRT
#                    (required if -species is not set)
#      -with_wm      Also transform  wm.nii.gz  if present
#      -h, --help    Show help and quit
#
#  Notes    :
#      * Templates are resolved relative to this script's directory.
#      * Requires FSL (robustfov / flirt / applywarp) in $PATH.
# -----------------------------------------------------------------------------
#  Author   : Yichun Huang  <ychunhuang@foxmail.com>
#  Updated  : 2025-06-09  (clean refactor, safer arg-handling)
# -----------------------------------------------------------------------------

set -euo pipefail

# ───────────────────────── helper functions ──────────────────────────
usage()  { grep -E "^#  " "$0" | cut -c4- ; }
log()    { printf '\e[1;36m[INFO]  %s\e[0m\n'  "$*"; }
warn()   { printf '\e[1;33m[WARN]  %s\e[0m\n'  "$*"; }
err()    { printf '\e[1;31m[ERROR] %s\e[0m\n' "$*" >&2; exit 1; }

# ───────────────────────── default values ────────────────────────────
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
TEMPLATE_DIR="$SCRIPT_DIR/template"
WITH_WM=0
SPECIES=""
BRAIN_SIZE=100 # TODO: test default
REFERENCE=""

# ───────────────────────── argument parsing ──────────────────────────
[[ $# -eq 0 ]] && { err "No arguments provided"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -out_path|--out_path)   OUT_PATH="${2:?missing dir}" ; shift 2 ;;
        -brainSize|--brainSize) BRAIN_SIZE="${2}"            ; shift 2 ;;
        -species|--species)     SPECIES="${2}"              ; shift 2 ;;
        -reference|--reference) REFERENCE="${2}"            ; shift 2 ;;
        -with_wm|--with_wm)     WITH_WM=1                    ; shift   ;;
        -h|--help)              usage ; exit 0               ;;
        *)                      err "Unknown option $1"      ;;
    esac
done

if [[ -n "${SPECIES:-}" ]]; then
    # Normalize species to make it case-insensitive (and robust to extra spaces)
    SPECIES="$(printf '%s' "$SPECIES" | tr '[:upper:]' '[:lower:]' | xargs)"

    case "$SPECIES" in
        macaque|rhesus|cynomolgus)
            REFERENCE="$TEMPLATE_DIR/Macaque/NMT_brain_05.nii.gz"
            ;;
        chimpanzee)
            REFERENCE="$TEMPLATE_DIR/Chimpanzee/ChimpYerkes29_T1w_0.8mm_brain.nii.gz"
            ;;
        marmoset)
            REFERENCE="$TEMPLATE_DIR/Marmoset/RIKENMarmoset15_AverageT1w_restore_dedrift_brain.nii.gz"
            ;;
        *)
            err "Unknown species: $SPECIES"
            ;;
    esac
else
    [[ -n "${REFERENCE:-}" ]] || err "If -species is not set, -reference is required"
fi

[[ -d "${OUT_PATH:-}" ]] || err "-out_path missing or not a directory"

# ───────────────────────── path setup ────────────────────────────────
JOB_DIR="${OUT_PATH%/}"
T1_IMG="$JOB_DIR/T1.nii.gz"
MASK_IMG="$JOB_DIR/brain_mask.nii.gz"
[[ -f $T1_IMG && -f $MASK_IMG ]] || err "T1.nii.gz or brain_mask.nii.gz not found in $JOB_DIR"

OUT_DIR="$JOB_DIR/ACPCAlignment"
RAW_BAK="$OUT_DIR/raw_backup"
mkdir -p "$RAW_BAK"

log "Reference template: $REFERENCE"
log "Brain size (FOV)  : $BRAIN_SIZE mm"

# ─────────────────────── backup originals ───────────────────────────
log "Backing up originals → $RAW_BAK"
cp "$T1_IMG"        "$RAW_BAK/T1.nii.gz"
fslmaths "$T1_IMG" -mas "$MASK_IMG" "$RAW_BAK/brain.nii.gz"
cp "$MASK_IMG"      "$RAW_BAK/brain_mask.nii.gz"
[[ $WITH_WM -eq 1 && -f $JOB_DIR/wm.nii.gz ]] && cp "$JOB_DIR/wm.nii.gz" "$RAW_BAK/wm.nii.gz"

# ─────────────────── field-of-view (robustfov) ───────────────────────
log "Step 1/4 : Robust FOV crop"
robustfov -i "$RAW_BAK/T1.nii.gz" \
            -m "$OUT_DIR/roi2full.mat" \
            -r "$OUT_DIR/robustroi.nii.gz" \
            -b "$BRAIN_SIZE"
convert_xfm -omat "$OUT_DIR/full2roi.mat" -inverse "$OUT_DIR/roi2full.mat"
flirt -in "$RAW_BAK/brain.nii.gz" \
        -ref "$OUT_DIR/robustroi.nii.gz" \
        -applyxfm -init "$OUT_DIR/full2roi.mat" \
        -out "$OUT_DIR/robustroi.nii.gz"

# ─────────────────── AC-PC rigid registration ───────────────────────
log "Step 2/4 : Rigid FLIRT to template (6 DOF)"
flirt -interp spline \
        -in  "$OUT_DIR/robustroi.nii.gz" \
        -ref "$REFERENCE" \
        -omat "$OUT_DIR/roi2std.mat" \
        -out "$OUT_DIR/acpc_final.nii.gz" \
        -dof 6

# ───────────────────── combine transforms ────────────────────────────
log "Step 3/4 : Concatenate matrices → acpc.mat"
convert_xfm -omat "$OUT_DIR/full2std.mat" \
            -concat "$OUT_DIR/roi2std.mat" "$OUT_DIR/full2roi.mat"
aff2rigid "$OUT_DIR/full2std.mat" "$OUT_DIR/acpc.mat"

# ───────────────────── apply to T1 / masks ───────────────────────────
log "Step 4/4 : Apply transform"
applywarp --rel --interp=spline \
            -i "$RAW_BAK/T1.nii.gz" \
            -r "$REFERENCE" \
            --premat="$OUT_DIR/acpc.mat" \
            -o "$JOB_DIR/T1.nii.gz"

applywarp --rel --interp=nn \
            -i "$RAW_BAK/brain_mask.nii.gz" \
            -r "$REFERENCE" \
            --premat="$OUT_DIR/acpc.mat" \
            -o "$JOB_DIR/brain_mask.nii.gz" \
            --interp="nn"

fslmaths "$JOB_DIR/T1.nii.gz" -mas "$JOB_DIR/brain_mask.nii.gz" "$JOB_DIR/brain.nii.gz"

if (( WITH_WM )); then
    if [[ -f $RAW_BAK/wm.nii.gz ]]; then
        log "Applying transform to WM mask"
        applywarp --rel --interp=nn \
                    -i "$RAW_BAK/wm.nii.gz" \
                    -r "$REFERENCE" \
                    --premat="$OUT_DIR/acpc.mat" \
                    -o "$JOB_DIR/wm.nii.gz" \
                    --interp="nn"

    else
        warn "-with_wm flag set but wm.nii.gz not found; skipping"
    fi
fi

log "AC-PC alignment finished ✔"
