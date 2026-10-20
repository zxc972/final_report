---
name: species-router
description: >-
  Detect species and image type (scalp vs brain) from a T1 NIfTI using the primx
  CNN router. Use proactively whenever species or segSpecies is required but the
  user has not provided it: if a NIfTI path is available, run this Skill before
  asking the user to identify the species, then report the prediction and ask for
  confirmation. Also use when the user asks to identify species or determine
  whether an image is skull-stripped.
compatibility: Requires primx segmentation router model (router_cnn_epoch_080.pth) and PyTorch.
metadata:
  module: seg
  step: router
---

# Species Router

## When to use this skill
Use this skill to infer the species and whether the input image is a full-head T1 (scalp) or brain-extracted image.

## What it does
- Runs `primx seg router` which calls `Moe_species_task.py`.
- A 3D CNN predicts the species and image type.

## Required inputs
- `inputImage`: Path to a NIfTI image (.nii or .nii.gz).

## Output
- `species`: predicted species name
- `imageType`: `scalp` or `brain`

## Command-line usage (primx)
```
primx seg router -input_image <IMAGE.nii.gz>
```

## Notes
- Species labels include marmoset, cynomolgus monkey, chimpanzee, rhesus monkey, and human.
