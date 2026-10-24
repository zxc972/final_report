# Round 14 group regional analysis on 6007

The registered `method:v14:group_regional_glm` now accepts group comparisons and continuous associations with covariates. It summarizes each subject's native atlas parcels, fits additive OLS with an intercept, and applies BH across every fitted partition of both hemispheres and selected metrics. Human development uses FastSurfer DKT. No real-model trial is enabled by this change.

## Operator catalog

```json
{"roots":[{"path":"/approved/synthetic_subject","subject_id":"s01","dataset":"synthetic","species_declared":"human","source":"synthetic"}],"participants_tables":[{"dataset":"synthetic","path":"/approved/participants.tsv","id_column":"subject_id","source":"synthetic","license":"synthetic"}]}
```

Tables are separate operator declarations, never subject roots. Only tables associated with approved datasets are staged into dedicated read-only mounts. CSV/TSV observations contain headers, row/nonempty counts, inferred types, categorical counts and ID matching. Missing/duplicate registered IDs or ambiguous tables are reported explicitly. The data card contains column names, without cell values.

## Intent and outputs

```json
{"measures":["thickness"],"regions":"DKT","comparison":"correlation","species":"human","subjects":["s01","s02"],"design":{"effect":"age","covariates":["sex"]}}
```

The example needs more subjects to leave positive residual degrees of freedom. An estimable continuous effect or a two-level factor is supported; categorical reference is optional. Designs include the intercept, use centered numeric terms, and treatment-code categorical covariates. Invalid design fields identify their locations; a missing design returns available columns. The cohort is restricted to one registered dataset/species and at most 128 subjects.

- `regional_values.csv`: the existing ROI schema and subject/hemisphere/metric/label identity.
- `group_results.csv`: hemisphere,metric,label_key,name,n,effect,estimate,se,t,df,p,q_fdr,effect_size,effect_size_kind,status.
- Group identity: hemisphere/metric/label_key. Every retained partition appears, including `skipped:<reason>` with empty statistics. Fitted status is `ok`. Effect is the exact column name, or `column[level]`. No aliases are mapped.
- FDR: one BH family across all fitted partitions, both hemispheres and all selected metrics. Skipped partitions are excluded from the family.
- Effect size: pooled Cohen d for an unadjusted factor, Pearson r for an unadjusted continuous term, partial r for adjusted models.

Inputs are referenced through `/work/inputs_manifest.json`; label sets remain explicit versioned JSON. The host checks the manifest hash before execution. Group execution cards are limited to 1500 characters, including at 128 subjects. The Agent writes its own numpy/scipy model; no host reference values are mounted or sent to it.

## Host verification and conclusions

The host reads each subject independently with `analysis_numeric_reference.roi_rows`, then runs the stdlib `analysis_group_stats.regional_glm`. It checks both declared CSVs with rtol=1e-7, atol=1e-9. The group reference cannot enter the convex-hull branch. Private values and differences remain outside `/work`; the frontend receives only each table's status and mismatch counts.

Group inference uses accepted/qualified/deferred/blocked rules: all required checks pass, soft warnings, an FDR-negative result with d_min>0.8, and a failed independent comparison respectively. Reporting must cover sample size/exclusions, FDR family, effect size, d_min and site/scanner composition or its unavailability. A missing item forces internal-review revision even when the model returns pass.

Power is a normal approximation at two-sided alpha=.05 and power=.8, using the actual design inverse covariance and residual degrees of freedom. Continuous effects are standardized slopes; factor effects use residual-SD units. It is not FDR-adjusted power or a noncentral-t sample-size guarantee. Physical scale/history and anatomical QC remain explicit limitations.

## FastSurfer layout

The observed IXI064 layout uses `scripts/recon-surf.done` and `recon-surf.log`; recon-all metadata is also recognized. `aparc.DKTatlas.mapped` belongs to the DKT family and supports regional summaries and asymmetry candidates.

Read-only links must resolve inside the same registered subject. External links remain rejected. For container access, a private input view normalizes internal absolute links into relative links while retaining the original link/target/resolved-path observation. Original source files and links are unchanged. Workspace writes retain strict no-link rules. Legacy navigation keeps its original policy.

## Immutable evidence and environment

`knowledge/research_v13` remains unchanged. `knowledge_analysis/method_graph_overlay_v14.json` and its SHA register the new method, project conditions and source notes; v13 identities take precedence, and unknown method IDs still fail. The notes distinguish this regional additive implementation from the FreeSurfer tutorial's vertexwise DODS example.

The 6007 engine is the existing strict Singularity 3.9.2 adapter. Scientific runtime: numpy 2.2.6, scipy 1.15.3, nibabel 5.4.2. Existing isolation options remain enforced. No service deployment/restart or model API request is part of this implementation.

Primary references: [FreeSurfer group GLM tutorial](https://surfer.nmr.mgh.harvard.edu/fswiki/FsTutorial/GroupAnalysis), [BH 1995](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x), [FastSurfer 2.4.2 recon-surf](https://github.com/Deep-MI/FastSurfer/blob/v2.4.2/recon_surf/recon-surf.sh).
