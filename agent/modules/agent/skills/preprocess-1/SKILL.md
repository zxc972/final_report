---
name: preprocess-1
description: Preprocess T1-weighted images (reorient, N4 bias correction, optional denoise/average, resampling) using primx neuro preprocess-1. Use when starting a PrimateX T1 preprocessing workflow.
compatibility: Requires primx CLI and containerized neuro pipeline tools (FSL, FreeSurfer, ANTs, MRtrix3).
metadata:
  module: neuro
  step: preprocess-1
---

# Preprocess-1

## When to use this skill
Use this skill at the start of the PrimateX workflow to preprocess raw T1-weighted images before segmentation or reconstruction.

## What it does
1. Re-orients raw T1-weighted images to standard (LAS) or sphinx position.
2. Performs N4 bias field correction (ANTs).
3. Optional denoising (ANTs DenoiseImage).
4. Optional averaging across repeats (FreeSurfer or HCP anatomical-average).
5. Resamples to species-specific isotropic voxel size.

## Required inputs
- `subjectId`: Output folder name for this subject.
- `workspaceDirectory`: Root workspace containing the subject folder.
- `t1Path`: Path to a T1 .nii/.nii.gz file or a folder of runs.
- `species`: Species label for voxel size and templates. Case-insensitive. `cynomolgus` and `rhesus` are accepted and treated as macaque.

## Optional inputs and flags
- `sphinx`: reorient to sphinx position (NHP-specific)
- `noStdOrient`: skip standard LAS reorientation
- `averageHcp`: use HCP anatomical-average instead of FS method
- `denoise`: enable ANTs denoising
- `keepTmp`: keep temporary files

## Output
- `T1.nii.gz` in `<workspaceDirectory>/<subjectId>`
- Additional intermediate files in `<out_path>/tmp` when temp retention is enabled

## Command-line usage (primx)
```
primx neuro preprocess-1 -t1_path <T1_PATH> -out_path <OUT_PATH> -species <Macaque|Chimpanzee|Marmoset>
```

## Notes
- Requires FSL, FreeSurfer, ANTs (N4), and MRtrix3 available in the container.
- The output directory is `<workspaceDirectory>/<subjectId>`.
