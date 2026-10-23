# Round 16: method condition canonicalization

This round imports `e767445` from `round16_canon.bundle`, based on `36d4c73`,
and evaluates algorithm 1 on the supplied 108 draft statements from 12 method
cards. The labels are marked `draft_by_claude_requires_human_review`; they have
not been promoted to human gold.

## Implementation and validation

- The canonicalizer remains byte-for-byte identical to the bundle. Its SHA-256
  is `9bf1171fc9fc831b7e9628c982888a7c5e74578bed377f5594f4f749cbbce4e9`.
- The model adapter in `tools/knowledge/provider_llm.py` uses the existing
  development gateway and `deepseek-v4.1-flash`, temperature 0.7 for all model
  arms, maximum 2048 completion tokens, and no agent/tool execution.
- Every HTTP attempt is reserved before sending and recorded with token usage.
  All arms and retries share a cap of 800 attempts. Unknown usage is explicit.
  Completed logical calls are cached by arm, statement and sample; successful
  calls are not repeated on resume.
- The runner freezes code, draft labels, original source files, defaults and
  provider metadata. It saves individual predictions, merged conditions,
  review queues, per-arm metrics, usage, and a full-arm error list.
- The original bundle tests passed: 7 new tests; full default backend 860 passed,
  14 skipped, 59 subtests passed (100.04 seconds).
- With the adapter: 17 targeted tests and 870 full-backend passes. After the
  gateway compatibility fix: **18 targeted tests; full default backend 871 passed,
  14 skipped, 59 subtests passed (98.43 seconds)**; 144 existing warnings.
- After isolating exhausted gateway failures and merging concurrent reviewed
  Round15 data tools: **19 targeted tests; complete default backend 877 passed,
  14 skipped, 59 subtests passed (103.66 seconds)**; 144 existing warnings.
- Protected-file mapping: all 100 available mapped files match their recorded
  digests. The historical protected set has 101 files with one unmapped file;
  that file is not claimed as rechecked.

## Evaluation protocol

The draft has 41 executable labels and 67 advisory labels. All 108 quotes match
the saved source text, so this sample does not test quote-rejection accuracy.
The unchanged defaults are rho=0.9, top-3 retrieval, lambda=0.3, tau=0.6,
delta=0.2, and K=5 (K=1 in the k1 arm). Model answers are sampled independently
between arms. Retrieval-only performs no model request.

The planned logical calls are full=540, k1=108, direct=108, retrieval_only=0.
Retries count against the 800 total request cap. Inputs and code were frozen
before the first completion request; manifest SHA-256:
`a02543da11e225423527f4e1acdc460577142e14eb35955fd6fd1a2cef4b5f2a`.

At 56 reserved attempts, HTTP200 responses exhausted at the 2048-token limit
exposed a gateway compatibility issue: some have null content rather than an
empty string. The initial adapter raised a provider error. The batch was paused
and only the transport/dispatch implementation was corrected: null length-
exhausted responses become empty answers (not retries), failed dispatch cancels
queued work, and 429 responses trigger a shared cooldown. All 56 attempts and
7 completed predictions were retained. Four in-flight attempts have unknown
usage and remain charged to the cap. The original ledger prefix and freeze are
archived under `freeze_history/`; model payload, algorithm, prompts, thresholds,
sampling, labels and source texts did not change. Continuation manifest SHA-256:
`e2f39520ae2a549dc17e954ddee76f76e70017e2483643b47c59d08796be0d26`.
Length-exhausted empty answers remain failures to supply a condition; no better
answer is substituted, and final diagnostics identify these responses.

One sample subsequently exhausted its three HTTP attempts because of 429
responses. At 75 reserved attempts, failed requests were isolated per statement
so other statements and arms can continue. These predictions are explicitly
`provider_error`, reported separately from semantic errors, and scored as no
valid prediction in the supplied aggregate metrics. No answer was resampled,
and all 13 completed predictions plus the raw ledger were retained. Current
continuation manifest SHA-256:
`054f9a031ef99326289bf925ea8551ae20ac80f5ffa610c1a3f90d61926cb126`.

Template accuracy includes the best proposed label of review items, as in the
supplied scorer. Executable classification requires accepted and non-advisory;
review/rejected/error results are not executable. Canonical keys are deduplicated
per method. Retrieval-only has no parameters, hence an empty predicted key set.
The error list reports any statement-level template, classification or key
mismatch, even where another statement supplies the same merged method key.

Final draft metrics and errors are in
`results/condition_canon_draft_v1/REPORT.md`, `summary.csv`, and `full_errors.md`.
The machine-readable prediction and request records permit an independent audit.
No parameter or prompt is changed in response to draft scores.

## Review boundary

Review `evaluation/condition_gold/gold_review_sheet_v1.csv` using the adjacent
README. After the user's review notification, only explicit user modifications
will be applied to a separate `gold_v1.json`; its change log and SHA-256 will be
frozen before the formal rerun. Formal sensitivity analysis and comparisons
against existing hand-written condition instances follow the formal result.
Conflicts await user decisions and never automatically overwrite knowledge.

This round creates no analysis run, preprocessing submission, deployment,
service restart, held-out processing, or PR merge. Credentials are loaded in
memory and omitted from logs and versioned outputs.
