---
name: workspace-ls
description: List all subject directories in a workspace folder. Use when the user has not provided a subject ID and you need to show them what subjects are available, or when they ask what subjects exist in a workspace. If no workspaceDirectory is given, the default test workspace is used automatically.
---

# Workspace Subject Listing

Use this skill to discover available subject IDs in a workspace before running a pipeline.

## Required inputs
None — all inputs are optional.

## Optional inputs
- `workspaceDirectory`: Path to the workspace root. If omitted, the default test workspace (`<repo>/tests`) is used.

## Output
- `workspaceDirectory`: The resolved workspace path that was scanned.
- `subjects`: List of subdirectory names (candidate subject IDs).

## Example tool call
```json
{}
```
or
```json
{
  "workspaceDirectory": "/data/primate_study"
}
```
