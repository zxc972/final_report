---
name: tail-log
description: Read the last N lines from a log file under a subject folder using tail. Use when the user asks to inspect recent log output.
---

# Tail Log Output

Use this skill to read the last few lines of a log file inside a subject directory.

## Required inputs
- `subjectId`: Subject folder name inside the workspace.
- `workspaceDirectory`: Workspace root path.
- `logPath`: Log file path relative to the subject directory.

## Optional inputs
- `lines`: Number of lines to read from the end (default 10).

## Output
- `path`: The resolved log file path.
- `output`: Tail output text.

## Example tool call
```json
{
  "subjectId": "YY_T1",
  "workspaceDirectory": "/path/to/workspace",
  "logPath": "logs/agent_pipeline_abcdef12.log",
  "lines": 20
}
```
