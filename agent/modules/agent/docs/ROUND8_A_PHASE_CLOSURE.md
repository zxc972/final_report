# Round 8 A: explicit phases and receipt-backed automatic closing

Base: 703978766a8c5bfc6d11d976c7096da351a36594. New mechanisms apply to product_graph_planner. Legacy prompt, validator module and the mechanical derive_manifest module remain byte-identical.

The host records unplanned, planned, sealed, executed_ok/executed_failed and finalized in protected versioned session records. Tool observations include a bounded state. A sealed script cannot be written at another path; resealing creates another retained plan version. An omitted run_python path resolves to the sealed path only in the product profile; other profile schemas retain required path.

After a successful production execution and its protected execution receipt, required files and CSV/JSON fields are checked. Automatic closing calls the extracted, otherwise unchanged existing finalization body without consuming an extra model/tool budget reservation. Failed columns are actionable; manual finalization cannot bypass the sealed minimum contract. An unchanged finalized artifact receipt is idempotent.

Ten library examples were actually executed on synthetic fixtures in the existing container, with a source digest binding. They are not subject outputs or expected answers. Large model-visible tool returns are archived in /work and summarized below 4,000 characters; only the model request view omits superseded source, while original generation responses and checkpoints remain auditable. Full execution bundles and versioned label sets remain readable.

Unit disclosures distinguish stored values, software conventions, physical scale verification and actual analysis rescaling from unverified input history.

Validation before paid runs:
- Default: 554 passed, 15 skipped, 54 subtests passed.
- Additional synthetic dependency checks: 39 passed, 1 skipped (host SciPy absent).
- Real isolated-container checks: 22 passed, 9 subtests passed; includes the three scripted recovery/automatic-closing scenarios.
- Frontend unchanged: 42 tests pass; TypeScript/build pass.
- Original knowledge/validator protected files unchanged.

Round 7 context-only replay uses tiktoken 0.12.0 cl100k_base, explicitly a proxy rather than a verified DeepSeek-v4 tokenizer. Actual old input was 1,495,371; per-call usage-calibrated after estimate is 505,114. System/tool definitions are held fixed in replay; new phase overhead and alternative model actions are not simulated. Full per-call estimates are retained in the external review audit, not sent to the Agent.
