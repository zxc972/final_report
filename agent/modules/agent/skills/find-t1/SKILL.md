---
name: find-t1
description: Find candidate T1 NIfTI files (.nii / .nii.gz) inside a subject directory. Use this after the user has chosen a subject ID but before running the pipeline, to discover the raw T1 image path automatically. Excludes known pipeline-generated output files.
---

# Find T1 Image

Use this skill to locate the raw T1 input image inside a subject directory before launching a pipeline.

## Required inputs
- `subjectId`: Subject folder name inside the workspace.

## Optional inputs
- `workspaceDirectory`: Workspace root path. Defaults to the agent's default workspace if omitted.

## Output
- `subjectRoot`: Resolved subject directory path.
- `candidates`: List of absolute paths to `.nii` / `.nii.gz` files found at depth 1–2 under the subject root, excluding known pipeline output filenames.

## Notes
- Raw T1 inputs are commonly found under `<subjectId>/anat/`.
- If multiple candidates are returned, show them to the user and ask which one is the T1.
- If exactly one candidate is returned, you may use it directly as `t1Path`.

## Example tool call
```json
{
  "subjectId": "ION003"
}
```

Or with an explicit workspace:
```json
{
  "subjectId": "ION003",
  "workspaceDirectory": "/home/user/primate_test"
}
```
