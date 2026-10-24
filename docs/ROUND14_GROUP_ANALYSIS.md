# Round 14: group-level regional analysis (in progress)

## Why
All end-to-end passes so far are single-subject (ROI summary, convex hull). Group comparison and age association are needed for the core thesis tasks (H02 age effect on IXI, M02 young vs aged macaques, multiverse analysis). The current planner never fills `analysis_scope.groups` / `design_columns`, so `comparison=group|correlation` is always blocked by `group_inference_sample`, and the backend has no statistics code.

## Done in this commit
- `backend/analysis_group_stats.py`: stdlib-only statistics for the host reference (no numpy/scipy/primatex_ops import):
  Student t tail (regularized incomplete beta), OLS with intercept, categorical and continuous terms, 1-df contrasts, Benjamini-Hochberg FDR, Cohen's d, Pearson r, design building from a participants table with explicit exclusion reasons, and `regional_glm` (one model per hemisphere/metric/label, FDR across all fitted regions).
- Cross-checked against NumPy/SciPy 1.18.1: max relative difference about 7e-13 over random designs (OLS, t, p, FDR, pooled t-test, Pearson), far inside the existing rtol 1e-7.
- `tests/test_round14_group_stats.py`: fixed SciPy reference values, design errors, exclusions, small-group skipping, FDR family; optional randomized SciPy check. Runs under pytest or as `python tests/test_round14_group_stats.py`.
- `knowledge_analysis/drafts/group_regional_glm.method.json`: method draft (slots, design, output contract, conditions, sources). Status `draft_not_registered`; pinned knowledge files are unchanged.
- Fix: `analysis_operations.suggested_operations` matched `mesh_surface_area`, but the registered method is `surface_mesh_area`, so `vertex_area` was never suggested. Both suffixes are now accepted.

## Integration checklist (next, needs the server test suite)
1. Participants table: let `AGENT_DATA_CATALOG` declare `participants_table` (path, id column) instead of treating a TSV root as a subject; carry `columns` / `nonempty_columns` into `product_view` so `design_variable` can evaluate.
2. Intent: add `design` to the plan intent (`effect`, `covariates`, `reference`); planner fills `analysis_scope.groups` / `design_columns` from the participants table.
3. Register the method: `method_requirements.json` (+sha), method graph card in a new release overlay (do not edit research_v13 in place), `constraint_probes.json` `method_commands` (+sha), `condition_templates.json` instances.
4. `analysis_operations`: suggested ops = per-subject `parcel_summary` as today, then the group model; `execution_bundle` columns from the draft contract.
5. `analysis_output_contract`: `GROUP_TYPES`, identity `[hemisphere, metric, label_key]`, expected rows = fitted regions.
6. `analysis_independent_numeric`: add `group_regional_glm` to `REGISTERED` with its own `reference_rows` branch (ROI reference per subject, then `regional_glm`); keep the hull branch unreachable for it.
7. `analysis_precision.FLOAT_COLUMNS` for estimate/se/t/p/q_fdr/effect_size.
8. Execution card must stay within 1500 characters.
9. Tests: planner with participants table, contract, reference binding, scripted end-to-end on synthetic multi-subject data.
