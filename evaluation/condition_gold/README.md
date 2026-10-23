# Round 16 draft condition labels and evaluation

`gold_draft_v1.json` and `gold_review_sheet_v1.csv` are the 108-statement draft
supplied in commit `e767445`. They have not been approved as human gold labels.
The draft files remain unchanged during evaluation.

## Draft run

The original canonicalizer is unchanged (SHA-256
`9bf1171fc9fc831b7e9628c982888a7c5e74578bed377f5594f4f749cbbce4e9`).
Defaults remain rho=0.9, retrieval top-3, K=5, lambda=0.3, tau=0.6, delta=0.2.
The four independent arms use the configured development gateway and
`deepseek-v4.1-flash` at temperature 0.7. The retrieval-only arm has no model call.

Run from the repository root, supplying the development configuration path
without copying its contents into this repository:

```bash
python tools/knowledge/run_condition_canonicalization.py \
  --gold evaluation/condition_gold/gold_draft_v1.json \
  --llm tools.knowledge.provider_llm:complete \
  --provider-config /path/to/development.env \
  --out results/condition_canon_draft_v1 --prepare-only
python tools/knowledge/run_condition_canonicalization.py \
  --gold evaluation/condition_gold/gold_draft_v1.json \
  --llm tools.knowledge.provider_llm:complete \
  --provider-config /path/to/development.env \
  --out results/condition_canon_draft_v1 --resume
```

The frozen manifest binds the draft, original sources, algorithm, runner,
adapter, defaults, model and sampling configuration. All 756 planned logical
calls fit in a shared cap of 800 HTTP attempts including retries. Checkpoints
and logical-call caches permit interruption without repeating successful calls.
The run creates no analysis session and invokes no analysis or preprocessing tool.

## Human review and later formal run

In a copy of the review sheet, use `reviewer_agree(Y/N)` to mark agreement.
For a changed label, set `reviewer_template`, `reviewer_parameters` (JSON), and
an optional explanation in `note`. Keep `id` and the original statement intact.
Unfilled rows are not treated as an approval or an automatic correction.

After the user's review notification, only explicit user changes will be merged
into a separate `gold_v1.json`, with a change log and a frozen SHA-256. The draft
run remains available. The formal rerun, tau/delta/K sensitivity analysis, and
comparison with hand-written condition instances are subsequent work. Existing
knowledge instances are never overwritten automatically when conflicts arise.
