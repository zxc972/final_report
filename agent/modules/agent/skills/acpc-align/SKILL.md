---
name: acpc-align
description: Align images to AC-PC orientation using primx neuro acpc-align. Use after brain extraction and before WM segmentation.
compatibility: Requires FSL and ANTs in the container.
metadata:
  module: neuro
  step: acpc-align
---
# ACPC Alignment

## When to use this skill

Use this skill to crop the field of view and align the brain to AC-PC orientation. It should be run after brain extraction and before WM segmentation.

## What it does

1. Crops field of view with FSL robustfov.
2. Performs 6-DOF rigid alignment to a species-specific reference template.
3. Combines transforms into a single rigid matrix (acpc.mat).
4. Applies transform to T1 and brain mask (optionally WM mask).

## Required inputs

- `subjectId`: Output folder name for this subject.
- `workspaceDirectory`: Root workspace containing the subject folder.
- `species`: Species label for template selection. Case-insensitive. `cynomolgus` and `rhesus` are accepted and treated as macaque.

## Optional inputs

- `brainSize`: brain size in mm (default 100). Set based on your knowledge of the species.
- `reference`: reference image for alignment
- `withWm`: apply the transform to WM mask

## Output

- Aligned output will **overwrite** the previous T1 and brainmask in `<workspaceDirectory>/<subjectId>`
- `acpc.mat` in the output directory

## Command-line usage (primx)

```
primx neuro acpc-align -out_path <OUT_PATH> -brainSize <100> -species <Macaque|cynomolgus|rhesus|Chimpanzee|Marmoset> -reference <REF>
```

## Notes

- If `species` is set, the script auto-selects a species-specific reference template.
- The original T1 and brainmask are overwritten. Backup are copied to `<subjectId>/ACPCAlignment/raw_backup`. Warn users accordingly.
