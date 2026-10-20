---
name: subject-ls
description: List files in a specific subfolder of a subject directory (ls -la). Best for targeted lookups when the user names a folder they want to inspect (e.g. "show me the logs folder", "what is in surf/"). For broad output overview or full directory layout, subject-tree is more efficient.
---

# Subject Folder Listing

Use this skill to list files in a subject output directory (or a subfolder) inside the PrimateX workspace.

## Required inputs
- `subjectId`: Subject folder name inside the workspace.
- `workspaceDirectory`: Workspace root path.

## Optional inputs
- `subPath`: Relative subfolder under the subject directory to list.

## Output
- `path`: The resolved path that was listed.
- `output`: Raw `ls -la` output.

## Example tool call
```json
{
  "subjectId": "YY_T1",
  "workspaceDirectory": "/path/to/workspace",
  "subPath": "logs"
}
```
