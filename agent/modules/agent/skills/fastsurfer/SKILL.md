---
name: fastsurfer
description: Run human cortical reconstruction using primx human fastsurfer. Use when the user wants FastSurfer processing for human T1 data.
compatibility: Requires primx CLI, modules/FastSurfer, and FreeSurfer runtime in the execution environment.
metadata:
  module: human
  step: fastsurfer
---

# Human FastSurfer

## When to use this skill
Use this skill for human T1 reconstruction with FastSurfer.

## What it does
1. Calls `primx human fastsurfer` through the agent backend task runner.
2. Passes `-t1_path`, `-id`, and `-out_path` to the FastSurfer wrapper.
3. Produces subject-level FastSurfer outputs under the workspace directory.

## Required inputs
- `subjectId`: Subject identifier used as FastSurfer `--sid`.
- `workspaceDirectory`: Root workspace directory used as FastSurfer output root.
- `t1Path`: Input human T1 path (.nii/.nii.gz file, or a directory containing NIfTI images).

## Optional inputs
- `species`: Optional. If provided, it should be `Human`.

## Output
- FastSurfer output folder under `<workspaceDirectory>/<subjectId>`.
- Agent task log under `<workspaceDirectory>/<subjectId>/logs/agent_pipeline_<taskId>.log`.

## Command-line usage (primx)
```
primx human fastsurfer -t1_path <T1_PATH> -id <SUB_ID> -out_path <WORKSPACE_DIR>
```

## Notes
- The FastSurfer wrapper in PrimateX always appends `--ignore_fs_version` for FreeSurfer 7.1 compatibility.
- `t1Path` supports both a direct NIfTI path and a directory path.
