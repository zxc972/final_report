# Round 17 development protocol — fixed before calls

The 108 statements were seen while designing v2. They are a development set,
not a held-out or formal independent test set. Use gold_reviewed_v1.json
unchanged: 91 confirmed, 11 corrected and 6 pending. Per the user instruction,
IDs 5, 13, 42, 76, 102 temporarily count as advisory and 41 as software; this
does not constitute final human approval or change their pending status.

- full_v2: bundled canonicalise_statement_v2, K=5, support=0.6, margin=0.2.
- k1_v2: the same algorithm with K=1.
- direct_v2: v2 definitions and source field, one sample, no allowed-vocabulary
  lines, no parameter normalisation, no type check and no vote.
- Vocabulary: every product_types.json type ID; every workflow_steps.json step
  ID plus recon-all. No per-statement vocabulary or label-based additions.
- Requested model: configured development deepseek-v4.1-flash, temperature 0.7,
  thinking disabled, JSON-object output, max_tokens 8192, timeout 180 seconds.
  Save observed model, finish reason, reasoning presence and reported reasoning
  token count; do not infer acceptance of settings merely from HTTP success.
- Each (arm, statement) may replace at most one length-limited sample with an
  identical prompt/settings. Preserve the original; replacement occupies that
  same vote position. No replacement for a semantic error or invalid parameter.
- Every HTTP attempt, including retry or replacement, consumes budget. Cap the
  development ledger at 1188 and the independent-card extraction ledger at 12,
  so their combined cap is 1200. Transport retries at most 3; shared 429 delay.
- Freeze source/label/code/vocabulary/configuration hashes before scored calls.
  Do not tune prompts, defaults or vocabularies from scores during this run.
- Rescore v1 full/k1/retrieval_only/direct from preserved predictions under the
  same reviewed labels, without calls or answer modification. Use the original
  strict canonical-key scorer and report both executable and negative classes.
- Prepare source-verified independent cards for four named methods. Provide a
  blind Claude annotation packet without any v1/v2 predictions or scores.
  No test gold or algorithm evaluation before the later annotation-freeze notice.

No analysis job, preprocessing, deployment, service restart, protected group
access or automatic knowledge-layer overwrite is authorised by this protocol.

A transport-only amendment after the first 124 metered requests smooths departures
(initial 2s, x1.25 after 429 up to 6s; x0.9 after 32 successes, minimum 2s).
Every request had a terminal ledger event before the runner was stopped. Preserve
all received samples and completed predictions, including transport failures.
Freeze history records the old/new manifests, ledger prefix and prediction hashes.
No sampling configuration, prompt, vocabulary, label or algorithm changed.
