---
name: list-samples
description: List the official sample subjects bundled with PrimateX, for users who want to try the pipeline without uploading their own data. Use this when the user asks to test/try the pipeline with sample/demo/example data, or asks what sample data is available.
---

# List Sample Subjects

Use this skill to discover which official sample subjects are available for testing,
before copying one into the user's own workspace with `use-sample-data`.

This scans the server's fixed sample pool — never the user's own workspace — so it
is safe to call regardless of which user is asking.

## Required inputs
None.

## Output
- `samples`: list of `{ sampleId, t1Path }` for each available sample subject.

## Notes
- This tool only lists samples; it never reads or writes the user's own workspace.
- After the user picks a sample, call `use-sample-data` to copy it into their own
  input directory before running the pipeline. Do NOT use the sample's raw path
  (under the shared sample pool) directly as `t1Path` for `run-pipeline` — always
  copy it into the user's namespace first.

## Example tool call
```json
{}
```
