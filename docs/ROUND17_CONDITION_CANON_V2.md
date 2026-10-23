# Round 17 condition canonicalization v2

The 108 previously observed statements are a development set. The bundled
reviewed labels remain unchanged, including six provisional user decisions.
The bundled algorithm file is byte-identical; all v1 AST nodes are preserved.

See [the full seven-arm development report](../results/condition_canon_dev_v2/REPORT.md),
[the complete full_v2 error and sample evidence](../results/condition_canon_dev_v2/FULL_V2_ERRORS_DETAILED.md),
[the metered request table](../results/condition_canon_dev_v2/all_call_usage.csv),
and [machine-readable evidence](evidence/round17_condition_canon_v2.json).

Both bundle commits (79d6bcb and 765bae2) were imported from the user-provided
round17_canon_v2.bundle. Imported default regression: 881 passed, 14 skipped;
final default regression: 894 passed, 14 skipped, 59 subtests passed (144 existing
warnings). The combined focused coverage is 36 passing tests. No live analysis
or preprocessing task was submitted and no service was deployed or restarted.

Implementation is in tools/knowledge/run_condition_canonicalization_v2.py and
provider_llm.py. Four v1 groups are rescored from frozen saved predictions with
zero calls; v2 uses full K=5, k1 K=1, and direct K=1 without allowed type/step
vocabulary, normalisation, type checking or voting. Scoring is unchanged.
Provider settings and actual gateway deviations are reported, including the
one transport-only continuation at 124 requests. All existing samples and
completed predictions were retained. The audit replays 324 predictions without
HTTP, checks every request prompt hash, all label/source/configuration hashes,
the two request caps summing to 1200, and the unmodified v1 predictions.

For independent evaluation, four new method cards contain 96 source-verified
statements; 45 statements from the same four fields as development are ready
for blind Claude annotation. Nine official source URLs are disjoint from the
old card sources. The previously seen NMT v2 overview was excluded. The
Workbench command is officially -surface-vertex-areas. Source-scope review
completed or narrowed 32 quotations/statements and preserves every original.
See [the blind annotation packet](../evaluation/condition_test_v1/claude_annotation_packet/README.md)
and [quote verification](../evaluation/condition_test_v1/quote_verification.json).
No independent labels, independent algorithm calls, sensitivity sweep or
knowledge-condition overwrite was performed. Claude annotation is a handoff
package, not a claimed annotation from an unavailable Claude tool or CLI.

Reproduce the paid run only with explicit budget authorisation; --resume checks
frozen inputs and replays cached samples. Read-only verification uses:

    python tools/knowledge/audit_condition_canon_v2.py --out results/condition_canon_dev_v2 --independent evaluation/condition_test_v1 --provider-config /path/to/development.env

Original HTTP ledgers and checkpoints remain only in local/development delivery.
Public Git contains sanitised predictions, token rows, source/label hashes,
review queues, the error evidence and the audit. Formal test evaluation waits
for the later notification that blind annotation is reviewed and SHA-frozen.
