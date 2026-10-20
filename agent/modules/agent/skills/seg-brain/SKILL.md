---
name: seg-brain
description: Skull-strip T1 images using primx seg brain to produce brain_mask.nii.gz and brain.nii.gz. Use after preprocess-1 and before ACPC alignment. Deep-learning segmentation steps share one execution slot; do not retry a step waiting for that resource or claim that maxConcurrentTasks can parallelize it.
compatibility: Requires primx segmentation models under modules/primx_seg/models and GPU if available.
metadata:
  module: seg
  step: brain
---

# Segmentation: Brain Extraction

## When to use this skill
Use this skill to perform brain extraction (skull stripping) on a T1 image. It is typically run after preprocess-1 and before ACPC alignment or WM segmentation.

## What it does
- Runs `primx seg brain` to infer brain mask and brain-only image.
- Writes outputs into the subject output directory.

## Required inputs
- `subjectId`: Output folder name for this subject.
- `workspaceDirectory`: Root workspace containing the subject folder.
- `segSpecies`: Segmentation species label. Case-insensitive (rhesus, cynomolgus, chimpanzee, marmoset, human).

## Optional inputs
- `t1Path`: Input T1 image path. If omitted, the backend uses `<workspaceDirectory>/<subjectId>/T1.nii.gz`.
- `modelDir`: override the default model root directory.

## Output
- `brain_mask.nii.gz`
- `brain.nii.gz`

## Command-line usage (primx)
```
primx seg brain -species <rhesus|cynomolgus|chimpanzee|marmoset|human> -input_image <T1.nii.gz> -output_dir <OUT_DIR>
```

## Notes
- If used after preprocess-1, set `-input_image` to the preprocessed T1 output, which is the `T1.nii.gz` in `<workspaceDirectory>/<subjectId>`.
- When rerunning only this step from the web or agent backend, `t1Path` may be omitted if `<workspaceDirectory>/<subjectId>/T1.nii.gz` already exists.
- `seg-brain` and `seg-wm` subprocesses share one execution slot because loading the deep-learning stack can cause high memory and BLAS pressure.
- Multiple subject pipelines may run concurrently, but only one deep-learning segmentation step runs at a time. Other non-segmentation steps retain normal parallelism.
- Treat `Waiting for segmentation resource` as expected. Do not submit a duplicate task, and do not suggest increasing `maxConcurrentTasks` to parallelize segmentation.
