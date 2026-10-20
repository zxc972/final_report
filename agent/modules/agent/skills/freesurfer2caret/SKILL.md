---
name: freesurfer2caret
description: Convert FreeSurfer outputs to HCP-style GIFTI/CIFTI and register surfaces using primx neuro freesurfer2caret. Use after rescale.
compatibility: Requires Connectome Workbench and FreeSurfer outputs in the container.
metadata:
  module: neuro
  step: freesurfer2caret
---

# Freesurfer2Caret

## When to use this skill
Use this skill to produce HCP-style surface outputs and register surfaces to fs_LR.

## What it does
- Converts surfaces to GIFTI and applies affine transforms.
- Generates midthickness, inflated, and sphere surfaces.
- Computes sulc/thickness/curvature metrics.
- Resamples to fs_LR (164k) and LowResMesh (default 32k).
- Optionally runs MSM sulc registration.
- Produces CIFTI dscalar/dlabel outputs.

## Required inputs
- `subjectId`: FreeSurfer subject ID.
- `workspaceDirectory`: Root workspace containing the subject folder.
- `species`: Species label. Case-insensitive. `cynomolgus` and `rhesus` are accepted and treated as macaque.

## Optional inputs
- `lowResMesh`
- `inflateExtraScale`
- `msmsulc`

## Output
- HCP-style GIFTI/CIFTI outputs under `<workspaceDirectory>/<subjectId>/<subjectId>/HCP_Stype_Dir`

## Command-line usage (primx)
```
primx neuro freesurfer2caret -id <SUB_ID> -out_path <OUT_PATH> -LowResMesh <32> -species <macaque|cynomolgus|rhesus|chimpanzee|marmoset>
```
