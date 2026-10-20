---
name: seg-wm
description: White-matter segmentation using primx seg wm to produce wm.nii.gz. Use after brain extraction (and optionally ACPC alignment). Deep-learning segmentation steps share one execution slot; do not retry a step waiting for that resource or claim that maxConcurrentTasks can parallelize it.
compatibility: Requires primx segmentation models under modules/primx_seg/models and GPU if available.
metadata:
  module: seg
  step: wm
---

# Segmentation: White Matter

## When to use this skill
Use this skill to generate a WM mask from a T1-Brain image. It typically runs after brain extraction and ACPC alignment.

## What it does
- Runs `primx seg wm` to infer white-matter mask.
- Writes the output into the subject output directory.

## Required inputs
- `subjectId`: Output folder name for this subject.
- `workspaceDirectory`: Root workspace containing the subject folder.
- `segSpecies`: Segmentation species label. Case-insensitive (rhesus, cynomolgus, chimpanzee, marmoset, human).

## Optional inputs
- `t1Path`: Input brain image path. If omitted, the backend uses `<workspaceDirectory>/<subjectId>/brain.nii.gz`.
- `modelDir`: override the default model root directory.

## Output
- `wm.nii.gz`

## Command-line usage (primx)
```
primx seg wm -species <rhesus|cynomolgus|chimpanzee|marmoset|human> -input_image <Brain.nii.gz> -output_dir <OUT_DIR>
```

## Notes
- If used after seg-brain or acpc-align, set `-input_image` to the brain-extracted T1 output, which is the `brain.nii.gz` in `<workspaceDirectory>/<subjectId>`.
- When rerunning only this step from the web or agent backend, `t1Path` may be omitted if `<workspaceDirectory>/<subjectId>/brain.nii.gz` already exists.
- `seg-brain` and `seg-wm` subprocesses share one execution slot because loading the deep-learning stack can cause high memory and BLAS pressure.
- Multiple subject pipelines may run concurrently, but only one deep-learning segmentation step runs at a time. Other non-segmentation steps retain normal parallelism.
- Treat `Waiting for segmentation resource` as expected. Do not submit a duplicate task, and do not suggest increasing `maxConcurrentTasks` to parallelize segmentation.
