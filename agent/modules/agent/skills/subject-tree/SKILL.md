---
name: subject-tree
description: Show the recursive directory tree of a subject output folder in a single call. Use when the user wants an overview of the output structure, all produced files, or the full layout of a subject directory. More efficient than multiple subject-ls calls for broad questions.
---

# Subject Directory Tree

Use this skill to render the complete directory structure of a subject output folder as a tree.
A single call replaces multiple `subject-ls` calls.

## Required inputs
- `subjectId`: Subject folder name inside the workspace.
- `workspaceDirectory`: Workspace root path.

## Optional inputs
- `subPath`: Relative subfolder under the subject directory to tree from (e.g. `082` for the FreeSurfer subject tree).
- `maxDepth`: How many levels deep to render (default 3). Increase to 5 or more to see deep FreeSurfer trees.

## Output
- `path`: The resolved root path.
- `tree`: Multi-line string with the full directory tree including file sizes.

## Example tool call
```json
{
  "subjectId": "082",
  "workspaceDirectory": "/home/yunfeng/Projects/primate_test",
  "maxDepth": 3
}
```

## Notes
- Directories appear with a trailing `/`; files show their byte size.
- For FreeSurfer output nested under `<subjectId>/<subjectId>/`, set `subPath` to the inner subject ID to drill in.
