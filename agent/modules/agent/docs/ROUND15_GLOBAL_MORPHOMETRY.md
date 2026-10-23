# Round 15 global morphometry

`product_graph_planner` supports `method:v15:global_morphometry` on one approved subject with `measures=["global_morphometry"]`, `regions="global"`, and `comparison="describe"`. The Agent writes and executes the complete program. `read_stats_measures` and `positive_mask_volume` are low-level operations, not complete analysis scripts.

Inputs are exact sealed paths: `aseg.stats` or `brainmask.mgz`, bilateral `aparc*.stats`, and optional bilateral pial surfaces. Stats products are typed as `StatsTable.AsegStats` and `StatsTable.CorticalParcStats`. No cortical regional correspondence is claimed.

Public CSV: `global_metrics.csv`, one row per subject. Identity is `(subject, species)`. `scale_status` is fixed by the protected observed processing history. Numeric fields are `brain_volume_mm3`, `etiv_mm3`, `total_area_mm2`, `mean_thickness_mm`, `hull_ratio`, `scale_k`, and five corresponding `stored_` metric columns. Missing values are empty, never invented zeros. CSV retains float precision; JSON uses native floats.

Definitions:

- Brain volume: `BrainSegVol`; positive-support brainmask volume is an explicitly disclosed fallback, not an equivalent segmentation definition. eTIV is separate.
- Area: sum of bilateral `WhiteSurfArea`.
- Thickness: hemisphere `MeanThickness` weighted by the same hemisphere white areas; not a pooled parcel `ThickAvg`.
- Hull ratio: sum of bilateral full-pial areas divided by the sum of their 3D convex-hull areas; not lGI or the mean of hemisphere ratios.
- Verified geometric enlargement factor k is removed by length/k, area/k², volume/k³. Intensity normalization called rescale is a different operation. Unknown processing scale leaves physical metric columns empty and preserves stored values. Software millimetres do not certify acquisition calibration or anatomical QC.

Host verification imports no `primatex_ops` and never mounts the reference worker into the generated-code sandbox. Configure `ANALYSIS_REFERENCE_PYTHON` to a Python environment installed with `requirements-reference.txt`. The host uses `analysis_global_reference.subject_globals`, binds its observations to the current sealed plan and execution receipt, and compares at atol=1e-9 / rtol=1e-7. Identity and numerical differences are counted separately. Reference rows do not enter model feedback.

Only completed, publicly valid, independently matched and internally reviewed subject outputs enter the protected global registry. Set `AGENT_GLOBAL_RESULTS_DIR` to a host directory outside all sandbox/input mounts. Repeated subjects do not inflate n. Changed outputs are excluded. The host calls `cross_species_summary` and writes `cross_species_global.csv`; with only human results it explicitly waits for the second species. The `global_cross_species_ratio` scope requires verified scale, an executed plausibility check and ratio measures; a plausibility warning qualifies the conclusion. It does not waive regional homology rules for regional analyses. These are descriptive species-mean ratios, not population or evolutionary causal inference.

The frozen `research_v13` release is unchanged. New definitions reside in the SHA-bound v15 overlay and the unified development knowledge store.

Sources: [FreeSurfer global statistics](https://surfer.nmr.mgh.harvard.edu/fswiki/MorphometryStats), [MGH/MGZ format](https://surfer.nmr.mgh.harvard.edu/fswiki/FsTutorial/MghFormat). Method-specific weighting and ratio-of-sums are explicit project definitions, not a claim that FreeSurfer prescribes this composite.
