# Macaque global acceptance and scale

This offline policy applies to declared macaques, starting with the 2026-10-23 acceptance protocol. It does not deploy a service or call a model.

## Public measurement contract

- Volume: final native `brainmask.mgz` positive support times valid MGH voxel volume. Do not use macaque eTIV or aseg-derived volumes.
- Area: sum final native white triangle areas.
- Thickness: per-hemisphere cortex-label vertex means, combined with final white-area weights. Retain finite zeros and report their count. Regional annotations are not used.
- Hull ratio: sum final pial areas divided by the sum of separate hemisphere convex-hull areas. This is a global ratio, not local gyrification index.
- Store both values as read and values corrected by the verified remaining linear factor k. Never divide by the historical enlargement after it has already been reverted. Unknown scale remains unknown.

The new `global_morphometry_species_policy.json` and its SHA bind requirements, planner input selection and operation suggestions. The human estimator is unchanged. Frozen `research_v13` assets are not edited.

## Independent audit

Run `tools/accept_macaque_globals.py --help` from a host Python with NumPy and NiBabel. Supply the selected non-held-out manifest, existing pilot audit, subject outer directory, a **new** provenance output directory, and the separate `analysis_global_reference_worker.py`. It refuses to overwrite acceptance records.

The audit records real pilot exit codes, raw hash stability, all six anatomical mesh restoration factors and exact residuals, final MGH spacing, thickness medians, direct white areas versus displayed stats, both voxel-edge and voxel-centre bounding boxes, and conflicting NIfTI transforms. It writes scale and acceptance JSON, full independent-reference subprocess receipts and input hashes. It does not repair any image, surface or statistics file.

White is an inner boundary and the positive brainmask support is an outer support. Keep their actual differences. A failed literal two-voxel comparison remains a failure of that criterion even when other evidence verifies processing scale. Distinguish `conditional_pass` from `pass`; expert anatomy QC and scanner calibration are separate.

## Bounded follow-up

`tools/macaque_batch_followup.py` monitors an existing first-subject worker, invokes the independent audit only after its actual completion, and releases explicitly selected subsequent subjects through a recorded gate. Conditional passes require direct user authorization for the specific prerequisite subject. Full passes can use the existing full-pass authorization.

Use a new provenance root and a hash-frozen runtime bundle, an explicit queue, the byte-identical original preprocessing runner/environment, and the verified model installation receipt. It refuses duplicate subject output/audit directories and held-out/non-rhesus rows, limits active subjects and resource use, retains failures without automatic retries and ends after a finite deadline. It never stops or restarts workers or services.

Original source inputs and derivatives, historical runs, credentials, licenses, subject images and private audit records must not be added to this source repository.
