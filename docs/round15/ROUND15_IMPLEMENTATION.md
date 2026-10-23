# Round 15: conclusion submission, global morphometry and data preparation

This is a review branch (`dev/round14-group-stats`), not a deployment. Existing services are unchanged. No held-out imaging is processed. Raw imaging, credentials, model checkpoints, execution workspaces and MRI QC images are not publication artifacts.

## Commits and tested versions

- `151a95f`: user-supplied Claude global reference bundle, based on `7f684bb`.
- `0d09847`: plan-bound conclusion scopes, rejection feedback, cached duplicate submissions and a four-submission ceiling.
- `b8e27a1`: single-subject global morphometry, public contract, host independent reference, source-bound scale observations and host-only eligible-subject aggregation.
- `bf0c967`: offline-only follow-up. A standalone hull-ratio request now selects the existing bilateral hull method rather than the new multi-metric global method. Three alias regressions pass. No fifth paid analysis was run.

A3 ran against immutable `0d09847`; the other three cases ran against immutable `b8e27a1`. The `bf0c967` follow-up is not represented as live-tested.

## Conclusion submission

The tool schema is generated from allowed scopes for the current sealed plan. Its enum and descriptions are visible to the model. Rejections include the allowed scopes and reason. Exact text/scope duplicates for the same execution receipt return the earlier result; distinct submissions are capped at four. Exhaustion yields unreviewed/deferred, never acceptance.

The prior A3 trace is retained. An offline replay using its unchanged conclusion text rejected the old scope and accepted `hemispheric_asymmetry` on the second submission. The new live A3 submitted once and ended qualified. No private expected numerical answer was supplied to the generation agent.

## Global public contract

Method: `method:v15:global_morphometry`. Single-subject descriptive analysis; no atlas is required.

Inputs: `aseg.stats` or positive `brainmask.mgz` support for volume, bilateral cortical parcellation stats for area/thickness, and optionally bilateral pial surfaces for the hull ratio. Stats types are `StatsTable.AsegStats` and `StatsTable.CorticalParcStats`. Frozen research_v13 content is unchanged; the new method uses a separate v15 overlay and updated mutable knowledge checksums.

`global_metrics.csv` has exactly one subject identity with these public columns:

```
subject,species,brain_volume_mm3,etiv_mm3,total_area_mm2,mean_thickness_mm,hull_ratio,scale_status,scale_k,stored_brain_volume_mm3,stored_etiv_mm3,stored_total_area_mm2,stored_mean_thickness_mm,stored_hull_ratio
```

- Brain volume is `BrainSegVol`, not eTIV. A positive-mask fallback has a different definition and is disclosed.
- Area is the sum of bilateral `WhiteSurfArea`; thickness is its weighted bilateral `MeanThickness`, not a mean of parcel ThickAvg values.
- Hull ratio is the sum of full pial triangle areas divided by the sum of their 3D convex-hull areas. It is not lGI or the mean of hemisphere ratios.
- Missing measures are empty, not zero. CSV retains full floating-point precision.
- Conversion is stored value / k^power (length 1, area 2, volume 3, ratio 0). Unknown scale history leaves physical columns and k empty while preserving stored measurements.

Execution cards are bounded to 1500 characters; full sealed bundles remain in /work. Host numeric checks use `analysis_global_reference.subject_globals` in an isolated reference interpreter and never import primatex_ops. Reference values are not returned to the model. Comparison is atol=1e-9, rtol=1e-7; identity and numeric differences are distinct.

Only native-completed cases with public contract, independent numeric comparison, valid final review and unchanged output hashes enter the host registry. Unique subjects are deduplicated. Host `cross_species_summary` writes species means, ratios and n. The ratio scope does not require regional homology, but does require verified scale and executed plausibility/measure checks. A single human result is waiting for both species, not a human–monkey finding.

## Real analyses (four authorized runs)

| Case | Subject | Native result | Contract | Host / external numeric | Internal review | Models / tools / executions |
|---|---|---|---|---|---|---|
| A3 asymmetry, C on | IXI064 | completed; qualified | pass | 372/372; pass | pass | 19 / 19 / 3 |
| Global metrics, C off | IXI064 | completed; qualified | pass | 12/12; pass | pass | 21 / 22 / 4 |
| A1 repeat | IXI294 | incomplete_review | pass | 310/310; pass | unreviewed after exhausted upstream retries | 15 / 19 / 2 |
| A2 repeat | IXI294 | blocked | pass | 4 missing physical fields; fail | pass, but host block prevails | 11 / 10 / 1 |

A2 selected global morphometry instead of hemisphere hull analysis; its arithmetic is not relabeled a successful A2. The offline dispatch correction preserves the failed case. Product and a separate NiBabel/NumPy/SciPy external implementation agree on all four pass/fail outcomes.

The four cases made 66 logical model calls and 71 HTTP attempts, including retries. Known tokens: 713,998 prompt +79,905 completion =793,903. Six attempts have unknown usage; failed/unknown requests are not treated as free. No verified monetary pricing was available. No additional paid analysis was made.

## Scale and scope

Human processing history is verified_not_rescaled (k=1) from actual FastSurfer adapter/argv provenance. N4 intensity rescaling is not coordinate enlargement. This is separate from independent physical acquisition calibration, which remains unverified. Visual/anatomical QC remains pending; qualified results are descriptive for the supplied subject.

For IXI064, the verified output contains BrainSegVol 1,240,008.851537 mm3, eTIV 1,546,465.620375 mm3, total WhiteSurfArea 181,553.3 mm2, weighted MeanThickness 2.5430522799860977 mm and summed pial/hull ratio 2.517774896223314. These values describe the processed reconstruction, not expert-validated anatomy or population differences.

## Reproducible data utilities

`tools/prepare_prime_structural.py` accepts an official participant CSV, completed tar.gz archive, explicitly chosen subject IDs and optional held-out list. It checks each individual's Macaca mulatta declaration, rejects held-out subjects, selects only anatomical files, refuses raw overwrites, records hashes and header units, and keeps repeated sessions within one subject.

Official links: [UC Davis](https://www.nitrc.org/frs/downloadlink.php/10421), [Institute of Neuroscience](https://www.nitrc.org/frs/downloadlink.php/10571). The ION selection is 32198, 32199, 32201; fascicularis records are excluded. The proposed UC Davis selection is 32125, 32126, 32127, all individually declared rhesus. Newcastle is not used. PRIME-DE site license information is CC-BY-NC-SA; version was not independently established. IXI remains CC BY-SA 3.0.

`tools/run_prime_primatex_pilot.py` records exact original PrimateX CLI commands, stage journals, real exit codes, sampled resource use, raw hashes and expected products. It mounts one input and source read-only, disables container networking, uses only a fresh writable output, and performs no retries or service management. Pass an existing reviewed `inside_environment.sh` and existing license path; license contents are never copied or printed. Other monkeys require pilot review before processing.

## Official rhesus checkpoints

[Official model repository](https://huggingface.co/CNAIL/PrimateX), public ungated revision `ab48594a75179c0cf427c5c41aa10655ebe29c8f`. The model card declares AGPL-3.0. `docs/round15/PRIMATEX_RHESUS_MODELS.json` records the six exact assets, sizes and official Git/LFS content identifiers. Checkpoints are not stored in Git.

```
python tools/download_primatex_models.py --output /path/to/PrimateX/modules/primx_seg/models
```

Only `rhesus_brain/` and `rhesus_wm/` are fetched; no account, token or agreement acceptance is performed. On 6007, direct Hugging Face was unreachable and the mirror returned 403. Assets were fetched by official HTTPS on the workstation, verified there and after SCP; the final hashes match official LFS/Git identifiers. Model download requests are not model-inference API calls.

## Tests and limits

- Final default backend: 837 passed, 14 skipped, 59 subtests passed; no failures.
- Real Singularity synthetic integrations: 25 passed, 14 subtests; no provider API calls.
- Global method/reference targeted tests: 11 passed (including three standalone folding aliases); Claude reference tests: 5 passed; explicit data-selection safety tests: 5 passed.
- An initial full-suite attempt omitted the repository `agent` PYTHONPATH entry and failed collection. Corrected test environment includes repo/agent, modules/agent, backend and the scientific reference site-packages; assertions were not relaxed. Earlier logs are retained.
- Existing frontend code is unchanged in Round15; no frontend deployment/restart occurred.
- Legacy prompt regression remains included in the full default suite.
- Available historical protected inventory: 100 mapped files match; one historically unmapped inventory entry remains unverified, not silently counted as passing.

The live batch is exhausted at four cases. Remaining work includes live retest of the offline A2 dispatch correction with separate authorization, completion/review of monkey reconstruction and scale, both-species host aggregation, and visual anatomical QC. A successful computation is not expert QC, a blind generalization test, or a population comparison.
