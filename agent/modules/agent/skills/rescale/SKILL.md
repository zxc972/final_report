---
name: rescale
description: Rescale FreeSurfer outputs from fake 1mm space back to native resolution using primx neuro rescale. Use after preprocess-3.
compatibility: Requires FreeSurfer utilities and Python helpers inside the container.
metadata:
  module: neuro
  step: rescale
---

# Rescale

## When to use this skill
Use this skill after preprocess-3 to rescale FreeSurfer outputs from the temporary 1mm space back to the species-specific native resolution.

## What it does
1. Backs up the 1mm subject directory.
2. Reconstructs key MRI volumes with corrected voxel sizes.
3. Rescales surfaces and recomputes metrics.

## Required inputs
- `subjectId`: FreeSurfer subject ID.
- `workspaceDirectory`: Root workspace containing the subject folder.
- `species`: Species label for voxel size. Case-insensitive. `cynomolgus` and `rhesus` are accepted and treated as macaque.

## Output
- Updated FreeSurfer subject tree under `<workspaceDirectory>/<subjectId>`

## Command-line usage (primx)
```
primx neuro rescale -id <SUB_ID> -out_path <OUT_PATH> -species <Macaque|Chimpanzee|Marmoset>
```

## Notes
- Species determines target voxel size (Macaque 0.5mm, Chimpanzee 0.8mm, Marmoset 0.2mm).
