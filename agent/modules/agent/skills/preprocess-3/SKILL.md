---
name: preprocess-3
description: Run FreeSurfer-based reconstruction initialization using primx neuro preprocess-3 (combined preprocess-3-1 and preprocess-3-2). Use after segmentation and ACPC alignment.
compatibility: Requires FreeSurfer license available in the container.
metadata:
  module: neuro
  step: preprocess-3
---

# Preprocess-3

## When to use this skill
Use this skill to run the recon-all initialization and surface preparation steps after brain/WM segmentation.

## What it does
Runs the combined preprocess-3 pipeline, including:
- Image truncation and resampling to a fake 1mm header
- FreeSurfer autorecon-1 without skull stripping
- Injection of DL brain/WM masks and atlas alignment
- WM surface fixes and normalization steps
- Reconstruction of surfaces and curvature metrics

## Required inputs
- `subjectId`: FreeSurfer subject ID (also the output folder name).
- `workspaceDirectory`: Root workspace containing the subject folder.
- `species`: Species label for templates and voxel size. Case-insensitive. `cynomolgus` and `rhesus` are accepted and treated as macaque.

## Optional inputs
- `threads`: CPU threads used by supported Preprocess-3 commands (`1`–`4`, default `2`).

## Output
- FreeSurfer subject tree under `<workspaceDirectory>/<subjectId>/<subjectId>`

## Command-line usage (primx)
```
primx neuro preprocess-3 -id <SUB_ID> -out_path <OUT_PATH> -species <Macaque|Chimpanzee|Marmoset> -threads <1|2|3|4>
```

## Notes
- To run this preprocess-3 skill, ensure that there are `brainmask.nii.gz` and `wm.nii.gz` files in the `<OUT_PATH>`, generated from previous segmentation steps.
- The pipeline includes steps described in Preprocess_3_1.sh and Preprocess_3_2.sh.
- FreeSurfer license must be bound in the container at `/opt/freesurfer-7.2.0/.license`.
- Species is case-insensitive; `cynomolgus` and `rhesus` map to macaque settings.
