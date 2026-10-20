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

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
MODULE_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"

# --- Parse key arguments required by Inference.py: -task, -input_image, -output_dir ---
TASK=""
INPUT_IMAGE=""
OUTPUT_DIR=""

ARGS=("$@")
i=0
while [ $i -lt ${#ARGS[@]} ]; do
    key="${ARGS[$i]}"
    case "$key" in
        -task)
            TASK="${ARGS[$((i+1))]}"
            i=$((i+2))
            ;;
        -input_image)
            INPUT_IMAGE="${ARGS[$((i+1))]}"
            i=$((i+2))
            ;;
        -output_dir)
            OUTPUT_DIR="${ARGS[$((i+1))]}"
            i=$((i+2))
            ;;
        *)
            i=$((i+1))
            ;;
    esac
done

# --- First run nnUNet inference ---
# [FIX] Removed exec to ensure the script can continue after Python finishes
python "$MODULE_DIR/Inference.py" "$@"

# --- If the task is brain, perform an FSL masking step in the output directory ---
if [ "${TASK:-}" = "brain" ]; then
    if ! command -v fslmaths >/dev/null 2>&1; then
        echo "[WARN] fslmaths not found, skipping cropping step based on brain_mask." >&2
        # Here we choose not to exit with error; exit 0 is acceptable depending on whether there is further logic
        exit 0
    fi

    if [ -z "${INPUT_IMAGE:-}" ] || [ -z "${OUTPUT_DIR:-}" ]; then
        echo "[WARN] Failed to parse -input_image or -output_dir, cannot run fslmaths masking." >&2
        exit 0
    fi

    MASK="${OUTPUT_DIR}/brain_mask.nii.gz"
    if [ ! -f "$MASK" ]; then
        echo "[WARN] brain_mask.nii.gz not found (${MASK}), skipping fslmaths masking." >&2
        exit 0
    fi

    # Output brain.nii.gz to the same output directory as the mask
    echo "[INFO] Using fslmaths with brain_mask to generate brain.nii.gz ..."
    fslmaths "${INPUT_IMAGE}" -mas "${MASK}" "${OUTPUT_DIR}/brain.nii.gz"
fi