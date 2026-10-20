---
name: use-sample-data
description: Copy an official sample subject (discovered via list-samples) into the current user's own input directory, so they can run the pipeline on it without uploading anything. Use this whenever the user wants to test/try the pipeline with sample/demo data, instead of browsing or using the raw sample path directly.
---

# Use Sample Data

Use this skill after `list-samples` to copy a chosen sample subject's T1 image
into the current user's own workspace (under their own `input/<subjectId>/T1/`),
respecting their configured namespace. This is the ONLY correct way to use the
official sample data — never call `subject-tree`, `find-t1`, or `run-pipeline`
directly against the raw sample pool path, since that would bypass the user's
own workspace and could mix data between users.

## Required inputs
- `sampleId`: The sample subject name returned by `list-samples`.

## Optional inputs
- `subjectId`: The subject ID to use in the user's own workspace. Defaults to `sampleId` if omitted.

## Output
- `t1Path`: Absolute path to the copied T1 file, inside the user's own workspace. Use this directly as `t1Path` for `run-pipeline`.
- `inputDir`: The directory the file was copied into.
- `subjectId`: The resolved subject ID.

## Notes
- The destination is always derived from the server-enforced workspace for the
  calling user — it cannot be redirected to another user's directory.
- After this call succeeds, proceed to `run-pipeline` using the returned `t1Path`
  and `subjectId`.

## Example tool call
```json
{
  "sampleId": "ION003"
}
```

Or with a custom subject ID:
```json
{
  "sampleId": "ION003",
  "subjectId": "my_test_run"
}
```
