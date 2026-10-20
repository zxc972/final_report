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
#  Preprocess_1.sh
# -----------------------------------------------------------------------------
#  Purpose :
#    1. Re‑orient raw T1‑weighted images to standard (or sphinx) position.
#    2. Perform intensity non‑uniformity (N4) correction.
#    3. Perform ANTs denoising (optional).
#    4. Optionally motion‑average repeats (FS) or HCP anatomical‑average.
#    5. Resample to isotropic voxel size (default 0.5 mm).
#
#  Usage :  ./Preprocess_1.sh -t1_path <dir or .nii/nii.gz file> -out_path <dir> [options]
#
#  Options
#    -sphinx           Re‑orient to sphinx position (non‑human primates)
#    -no_std_orient    Skip re-orientation to standard (LAS) position
#    -average_HCP      Use HCP anatomical‑average instead of FreeSurfer (FS)
#    -species          macaque|cynomolgus|rhesus 0.5mm, chimpanzee 0.8mm, marmoset 0.2mm (Default: macaque)
#    -denoise          Denoise images using ANTs DenoiseImage (default: no)
#    -tmp              Keep temporary files (for QC); default is to remove
#    -h | --help       Show help and exit
#
#  Notes  :
#    * Requires FSL, FreeSurfer, ANTs (N4), and MRtrix3 in $PATH.
#    * Written & maintained by Yichun Huang — 2025‑06‑09
# -----------------------------------------------------------------------------

set -euo pipefail

# ------------------------------- logging helpers ------------------------------
log()  { printf '\e[1;36m[INFO]  %s\e[0m\n'  "$*"; }
warn() { printf '\e[1;33m[WARN]  %s\e[0m\n'  "$*"; }
err()  { printf '\e[1;31m[ERROR] %s\e[0m\n' "$*" >&2; exit 1; }

# ---------------------------------- usage ------------------------------------
usage() { grep -E "^#  " "$0" | cut -c4- ; }

# ------------------------------ default values --------------------------------
SPHINX=0                 # 0 = no sphinx re‑orient, 1 = sphinx
REORIENT_STD=1           # 1 = do standard re-orientation, 0 = skip
DENOISE=0                # 1 = denoise, 0 = skip
AVG_METHOD="FS"          # FS (default) | HCP
SPECIES=Macaque          # macaque 0.5mm (incl. cynomolgus/rhesus), chimpanzee 0.8mm, marmoset 0.2mm
KEEP_TMP=0               # 0 = remove, 1 = keep
MRTRIX_BIN="mrgrid"      # override if not in $PATH
MRI_MOTION="mri_motion_correct.fsl" # FS motion‑average script
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")" # directory of this script
SCRIPTS_PATH="${SCRIPT_DIR}/pyscript" # HCP AnatomicalAverage.sh

# -------------------------------- arg parse ----------------------------------
[[ $# -eq 0 ]] && { err "No arguments provided"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        -t1_path)   T1_DIR="${2:?missing T1 dir}"     ; shift 2 ;;
        -out_path)  OUT_DIR="${2:?missing out dir}"    ; shift 2 ;;
        -sphinx)    SPHINX=1 ; shift ;;
        -no_std_orient) REORIENT_STD=0 ; shift ;;
        -average_HCP)   AVG_METHOD="HCP" ; shift ;;
        -species)   SPECIES="${2}" ; shift 2 ;;
        -denoise)   DENOISE=1 ; shift ;;
        -tmp)       KEEP_TMP=1 ; shift ;;
        -h|--help)  usage ; exit 0 ;;
        *) err "Unknown option: $1" ;;
    esac
done

# ------------------------------ t1_path input handling -----------------------
# Support: a folder of runs OR a single .nii/.nii.gz file
T1_INPUT="${T1_DIR:-}"
[[ -z "${T1_INPUT}" ]] && err "-t1_path is required"

T1_MODE="dir"
T1_GLOB_DIR="$T1_INPUT"
T1_SINGLE_FILE=""
if [[ -f "$T1_INPUT" ]]; then
    case "$T1_INPUT" in
        *.nii|*.nii.gz) ;;
        *) err "-t1_path must be a directory or a .nii/.nii.gz file (got: $T1_INPUT)" ;;
    esac
    T1_MODE="file"
    T1_GLOB_DIR="$(cd "$(dirname "$T1_INPUT")" && pwd)"
    T1_SINGLE_FILE="$(basename "$T1_INPUT")"
elif [[ -d "$T1_INPUT" ]]; then
    T1_MODE="dir"
    T1_GLOB_DIR="$T1_INPUT"
else
    err "-t1_path not found: $T1_INPUT"
fi

# Normalize species input (trim + case-insensitive handling)
SPECIES="$(printf '%s' "${SPECIES:-}" | awk '{$1=$1}1' | tr '[:upper:]' '[:lower:]')"

# Set voxel size based on species (case-insensitive)
case "$SPECIES" in
    macaque|cynomolgus|rhesus)  VOXEL_SIZE=0.5 ;;
    chimpanzee)                 VOXEL_SIZE=0.8 ;;
    marmoset)                   VOXEL_SIZE=0.2 ;;
    *)                          err "Unknown species: $SPECIES (allowed: macaque|cynomolgus|rhesus|chimpanzee|marmoset)" ;;
esac
log "Species: $SPECIES, Voxel size: ${VOXEL_SIZE}mm"

# ------------------------------ sanity checks --------------------------------
for v in T1_DIR OUT_DIR; do [[ -z "${!v:-}" ]] && err "-$v is required"; done
command -v N4BiasFieldCorrection >/dev/null || err "ANTs (N4) not found";
command -v fslreorient2std >/dev/null || err "FSL not found"; 
command -v mri_convert >/dev/null || err "FreeSurfer not found";
command -v $MRTRIX_BIN            >/dev/null || err "MRtrix3 binary not found";

# ------------------------------ path set‑up ----------------------------------
JOB_DIR="${OUT_DIR%/}"
ORIG_DIR="$JOB_DIR/orig"
REORIENT_DIR="$JOB_DIR/reorient"
N4_DIR="$JOB_DIR/N4_T1"
TMP_DIR="$JOB_DIR/tmp"
mkdir -p "$ORIG_DIR" "$REORIENT_DIR" "$N4_DIR" "$TMP_DIR"

# --------------------------- copy source images ------------------------------
log "Copying source images → $ORIG_DIR"
idx=1
shopt -s nullglob

if [[ "$T1_MODE" == "file" ]]; then
    # One explicit file
    fn="$T1_GLOB_DIR/$T1_SINGLE_FILE"
    dest="$ORIG_DIR/raw_${idx}_T1.nii.gz"
    if [[ "$fn" == *.nii ]]; then
        [[ -f "$dest" ]] || gzip -c "$fn" > "$dest"
    else
        cp -n "$fn" "$dest"
    fi
    ((idx++))
else
    # A directory of runs
    cd "$T1_GLOB_DIR"
    for fn in *.nii.gz *.nii; do
        dest="$ORIG_DIR/raw_${idx}_T1.nii.gz"
        if [[ "$fn" == *.nii ]]; then
            [[ -f "$dest" ]] || gzip -c "$fn" > "$dest"
        else
            cp -n "$fn" "$dest"
        fi
        ((idx++))
    done
fi

shopt -u nullglob

# --------------------------- re‑orientation ----------------------------------
if (( SPHINX )); then
        log "Reorienting to sphinx position"
    for fn in "$ORIG_DIR"/*.nii.gz; do
        mri_convert "$fn" "$fn" --sphinx
    done
fi

if (( REORIENT_STD )); then
    log "Reorienting to standard orientation"
    cd "$ORIG_DIR"
    for fn in *.nii.gz; do
        base="${fn%.nii.gz}"
        fslreorient2std "$fn"      "$REORIENT_DIR/${base}_std.nii.gz"
        fslorient -setqformcode 1  "$REORIENT_DIR/${base}_std.nii.gz"
        fslorient -setsformcode 1  "$REORIENT_DIR/${base}_std.nii.gz"
    done
else
    log "Skipping standard reorientation"
    cd "$ORIG_DIR"
    for fn in *.nii.gz; do
        base="${fn%.nii.gz}"
        cp "$fn" "$REORIENT_DIR/${base}_std.nii.gz"
    done
fi

# ------------------------------ N4 INU corr ----------------------------------
log "Running N4 biasfield correction"
cd "$REORIENT_DIR"
for fn in *_std.nii.gz; do
    base="${fn%_std.nii.gz}"
    N4BiasFieldCorrection -d 3 -i "$fn" -o "$N4_DIR/${base}_N4.nii.gz"
done

# ------------------------------ denoise (optional) ---------------------------
if (( DENOISE )); then
    log "Denoising images"
    for fn in "$N4_DIR"/*_N4.nii.gz; do
        base="${fn%_N4.nii.gz}"
        DenoiseImage -d 3 -i "$fn" \
            -o "$base"_denoise.nii.gz -n Gaussian
        mv "$base"_denoise.nii.gz "$fn"
    done
else
    log "Skipping denoising"
fi

# ---------------------- average ---------------------------
cd "$N4_DIR"
shopt -s nullglob
t1_files=(*.nii.gz)
num_img=${#t1_files[@]}
log "Found $num_img N4corrected T1 image(s)"

if [[ $AVG_METHOD == "HCP" ]]; then
    log "Averaging using HCP AnatomicalAverage (n=$num_img)"
    if (( num_img == 1 )); then
        cp "${t1_files[0]}" "$JOB_DIR/T1_process_1.nii.gz"
    else
        "$SCRIPTS_PATH/AnatomicalAverage.sh" -n -o "$JOB_DIR/T1_process_1.nii.gz" "${t1_files[@]}"
    fi
    else  # FS default
        log "Averaging using FreeSurfer motioncorrect (n=$num_img)"
    if (( num_img == 1 )); then
        cp "${t1_files[0]}" "$JOB_DIR/T1_process_1.nii.gz"
    elif (( num_img >= 2 )); then
        $MRI_MOTION -o "$JOB_DIR/T1_process_1.nii.gz" -wild "${t1_files[@]}"
    fi
fi

# ---------------------- resample ---------------------------
resample() {
    inp="$1"; out="$2"; size="$3";
    $MRTRIX_BIN "$inp" regrid -voxel "$size" "$out" -force
}

resample "$JOB_DIR/T1_process_1.nii.gz" "$JOB_DIR/T1.nii.gz" "$VOXEL_SIZE"

# ----------------------------- cleanup tmp ----------------------------------
if (( KEEP_TMP == 0 )); then
    log "Removing temporary directory"
    rm -rf "$TMP_DIR"
else
    warn "Keeping temporary files in $TMP_DIR"
fi

log "Preprocess 1 completed successfully"
