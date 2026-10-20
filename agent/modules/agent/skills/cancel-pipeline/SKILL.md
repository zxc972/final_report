---
name: cancel-pipeline
description: Cancel a running PrimateX pipeline task by taskId. Use when the user requests cancellation.
metadata:
  module: pipeline
  step: cancel
---

# Cancel Pipeline

## When to use this skill
Use this skill to cancel a running pipeline task by task ID.

## Required inputs
- `taskId`: The task identifier returned by run-pipeline or step tools.

## What it does
- Marks the task as cancelled.
- Attempts to terminate the running process.

## Command-line usage
No primx CLI call is required. This skill cancels a task in the agent backend.
