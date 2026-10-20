---
name: run-pipeline
description: Run a multi-step PrimateX workflow by executing an ordered list of steps. Use when the user wants a full T1 preprocessing and cortical reconstruction pipeline. The seg-brain and seg-wm subprocesses share one execution slot while other steps retain normal task parallelism.
compatibility: Requires primx CLI and containerized neuro/segmentation tools.
metadata:
  module: pipeline
  step: multi
---

# Run Pipeline

## When to use this skill
Use this skill to execute multiple PrimateX steps in order when a full workflow is requested.

## What it does
- Validates the ordered list of steps.
- Runs each step sequentially with logging.
- Returns a task ID for status tracking.
- When re-running existing data, only `preprocess-3` and `rescale` need step-specific preparation:
  - `preprocess-3` replaces the FreeSurfer reconstruction directories for that subject.
  - `rescale` restores the saved 1mm FreeSurfer backup before regenerating native-resolution outputs.
  - Earlier steps (`preprocess-1`, `seg-brain`, `acpc-align`, `seg-wm`) can overwrite their own files and do not require deleting the whole subject output.

## Required inputs
- `subjectId`: Output folder name for this subject.
- `workspaceDirectory`: **Always use the value from Context verbatim.** It already encodes the user's namespace (e.g. `/data/tests/<userId>/output`). Do NOT substitute the raw test data folder or any other path.
- `steps`: Ordered list of steps to execute.

## Optional inputs
- `t1Path` (required for `preprocess-1` and `fastsurfer`; optional for rerunning `seg-brain` or `seg-wm` when the expected upstream output already exists)
- `species` (required for neuro steps; optional for `fastsurfer`, if provided use `Human`)
- `segSpecies` (required for segmentation steps; case-insensitive)
- `modelDir`, `brainSize`, `reference`, `lowResMesh`
- `threads`: CPU threads used by supported Preprocess-3 commands (`1`–`4`, default `2`). This is independent of the number of concurrently running tasks.
- Flags: `sphinx`, `noStdOrient`, `averageHcp`, `denoise`, `keepTmp`, `withWm`, `inflateExtraScale`, `msmsulc`

## Output
- Logs: `<workspaceDirectory>/<subjectId>/logs/agent_pipeline_<taskId>.log`
- Intermediate and final outputs from each step.

## Deep-learning segmentation scheduling
- Multiple subject pipelines may execute concurrently.
- Immediately before starting a `seg-brain` or `seg-wm` subprocess, the runner acquires a shared segmentation resource; it releases that resource as soon as the step exits.
- Only one deep-learning segmentation step runs at a time. Preprocessing, alignment, reconstruction, and export steps retain their configured parallelism.
- Do not retry or duplicate a task showing `Waiting for segmentation resource`.
- `maxConcurrentTasks` controls general pipeline concurrency; it does not override the single segmentation execution slot.

## Command-line usage (primx)
```
primx neuro preprocess-1 -t1_path <T1_PATH> -out_path <OUT_PATH> -species <Macaque|Chimpanzee|Marmoset>
primx seg brain -species <rhesus|cynomolgus|chimpanzee|marmoset|human> -input_image <T1.nii.gz> -output_dir <OUT_DIR>
primx neuro acpc-align -out_path <OUT_PATH> -brainSize <100> -species <Macaque|Chimpanzee|Marmoset>
primx seg wm -species <rhesus|cynomolgus|chimpanzee|marmoset|human> -input_image <T1.nii.gz> -output_dir <OUT_DIR>
primx neuro preprocess-3 -id <SUB_ID> -out_path <OUT_PATH> -species <Macaque|Chimpanzee|Marmoset> -threads <1|2|3|4>
primx neuro rescale -id <SUB_ID> -out_path <OUT_PATH> -species <Macaque|Chimpanzee|Marmoset>
primx neuro freesurfer2caret -id <SUB_ID> -out_path <OUT_PATH> -LowResMesh <32> -species <Macaque|Chimpanzee|Marmoset>
primx human fastsurfer -t1_path <T1_PATH> -id <SUB_ID> -out_path <WORKSPACE_DIR>
```

## Step-only rerun input defaults
- If `seg-brain` is run without `t1Path`, the backend uses `<workspaceDirectory>/<subjectId>/T1.nii.gz`.
- If `seg-wm` is run without `t1Path`, the backend uses `<workspaceDirectory>/<subjectId>/brain.nii.gz`.
- If those files do not exist, ask the user for the exact image path before running the task.
