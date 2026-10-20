---
name: pipeline-status
description: Fetch the status of a running PrimateX pipeline task by taskId. Use when the user asks about task progress or errors.
metadata:
  module: pipeline
  step: status
---

# Pipeline Status

## When to use this skill
Use this skill to retrieve task state, progress, and error messages for a given task ID.

## Required inputs
- `taskId`: The task identifier returned by run-pipeline or step tools.

## Output fields
- `status`, `currentStep`, `progress`, `message`
- `startTime`, `endTime`, `error`, `logPath`

## Command-line usage
No primx CLI call is required. This skill queries the agent backend task registry.
