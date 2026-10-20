# PrimateX Neuro Pipeline (`modules/neuro_pipeline`)

This module contains the non-human primate structural MRI preprocessing and cortical surface reconstruction workflow used by PrimateX. It combines shell scripts, small Python utilities, FreeSurfer, FSL, ANTs, MRtrix3, Connectome Workbench, and the `primx` CLI wrapper.

The main workflow is:

1. `Preprocess_1.sh`: preprocess raw T1w images.
2. `primx seg brain`: generate `brain_mask.nii.gz` and `brain.nii.gz`.
3. `ACPC_Alignment.sh`: rigid AC-PC alignment after brain extraction.
4. `primx seg wm`: generate `wm.nii.gz`.
5. `Preprocess_3_1.sh`: FreeSurfer autorecon-1, DL mask/WM fixes, atlas-based MRI preparation.
6. `Preprocess_3_2.sh`: surface reconstruction and FreeSurfer spherical registration.
7. `Rescale.sh`: convert fake-1 mm FreeSurfer outputs back to species-native resolution.
8. `Freesurfer2CaretandRegister.sh`: convert to Workbench GIFTI/CIFTI and register to fs_LR.
9. Optional `LabelResample.sh`: resample external fs_LR labels back to native FreeSurfer `.annot`.

![PRIMATEX_HOME Pipeline Overview](../../Figures/Pipeline.jpg)

## Module Contract

**Core inputs**

- Raw T1w image as a single `.nii` / `.nii.gz` file or a directory of `.nii` / `.nii.gz` runs.
- Brain mask `brain_mask.nii.gz` from the segmentation module.
- Optional white-matter mask `wm.nii.gz` from the segmentation module.
- Subject ID (`-id`) and work directory (`-out_path`) for FreeSurfer steps.
- Species selection: macaque/cynomolgus/rhesus, chimpanzee, or marmoset depending on script.

**Core outputs**

- Preprocessed volume outputs in `<out_path>`:
  - `T1.nii.gz`
  - `brain_mask.nii.gz`
  - `brain.nii.gz`
  - `wm.nii.gz`
  - `ACPCAlignment/` when ACPC alignment is run
- FreeSurfer subject tree:
  - `<out_path>/<SUB_ID>/mri`
  - `<out_path>/<SUB_ID>/surf`
  - `<out_path>/<SUB_ID>/label`
  - `<out_path>/<SUB_ID>/stats`
- HCP/Workbench-style outputs:
  - `<out_path>/<SUB_ID>/HCP_Style_Dir/Native`
  - `<out_path>/<SUB_ID>/HCP_Style_Dir/fsaverage`
  - `<out_path>/<SUB_ID>/HCP_Style_Dir/fsaverage_LR<LowResMesh>k`

**Execution**

- Root scripts are the implementation targets.
- `bin/*.sh` scripts are stable wrappers used by `workflows/primx_cli/primx`.
- Templates are resolved relative to `modules/neuro_pipeline/template/`.
- Helper scripts are resolved relative to `modules/neuro_pipeline/pyscript/`.
- Scripts log to stdout/stderr by default. With `primx --log_dir <dir> ...`, output is tee'd to a command-specific log file.

## Species Support

| Species input | Normalized behavior | Native voxel size |
| --- | --- | --- |
| `macaque`, `cynomolgus`, `rhesus` | Macaque templates/logic | 0.5 mm |
| `chimpanzee` | Chimpanzee templates/logic | 0.8 mm |
| `marmoset` | Marmoset templates/logic | 0.2 mm |

Most scripts accept species case-insensitively and map `cynomolgus`/`rhesus` to Macaque. `LabelResample.sh` is the exception in the current code: it expects `Macaque`, `Chimpanzee`, or `Marmoset` exactly.

Macaque and Marmoset use atlas-based aseg paths in `Preprocess_3_1.sh`;
Chimpanzee retains its species-specific GCA path because the repository has no
compatible whole-brain FreeSurfer label atlas to warp. The Marmoset atlas and experimental
hybrid-aseg outputs should be validated carefully before production analyses.

## Unified CLI

The neuro scripts are usually launched through `primx`:

```shell
primx=/path/to/PrimateX/workflows/primx_cli/primx

primx neuro preprocess-1 ...
primx neuro acpc-align ...
primx neuro preprocess-3 ...
primx neuro rescale ...
primx neuro freesurfer2caret ...
primx neuro label-resample ...
primx neuro image-reorient ...
```

`primx neuro preprocess-3` runs `Preprocess_3_1.sh` followed by `Preprocess_3_2.sh`. The split commands remain available as `preprocess-3-1` and `preprocess-3-2`.

## `Preprocess_1.sh`

### Purpose

Initial T1 preprocessing:

1. Accept one `.nii` / `.nii.gz` file or a directory of T1 runs.
2. Optionally reorient to sphinx position.
3. Reorient to FSL standard orientation unless `-no_std_orient` is set.
4. Run N4 bias-field correction.
5. Optionally denoise with ANTs `DenoiseImage`.
6. Average repeated runs using FreeSurfer motion correction or HCP anatomical averaging.
7. Resample to species-native isotropic voxel size.

### Usage

```shell
bash Preprocess_1.sh \
  -t1_path <dir-or-T1.nii[.gz]> \
  -out_path <out_path> \
  [-sphinx] [-no_std_orient] [-average_HCP] \
  [-species <species>] [-denoise] [-tmp]
```

Options:

- `-t1_path`: required. Directory of runs or one `.nii` / `.nii.gz` file.
- `-out_path`: required. Working directory where `T1.nii.gz` is written.
- `-sphinx`: run `mri_convert --sphinx` before standard reorientation.
- `-no_std_orient`: skip `fslreorient2std`.
- `-average_HCP`: use `pyscript/AnatomicalAverage.sh`; default is FreeSurfer `mri_motion_correct.fsl`.
- `-species`: case-insensitive species selector. Default: `Macaque`.
- `-denoise`: run ANTs denoising after N4.
- `-tmp`: keep temporary files.

Example:

```shell
singularity exec -B "$surf":"$surf" "$container" \
  "$primx" neuro preprocess-1 \
  -t1_path "$surf/$subjid/T1" \
  -out_path "$surf/$subjid" \
  -species macaque \
  -denoise
```

## Segmentation Interface

Segmentation lives in `modules/primx_seg`, but the neuro workflow expects its outputs.

```shell
singularity exec --nv -B "$surf":"$surf" "$container" \
  "$primx" seg brain \
  -species cynomolgus \
  -input_image "$surf/$subjid/T1.nii.gz" \
  -output_dir "$surf/$subjid"

singularity exec --nv -B "$surf":"$surf" "$container" \
  "$primx" seg wm \
  -species cynomolgus \
  -input_image "$surf/$subjid/brain.nii.gz" \
  -output_dir "$surf/$subjid"
```

Outputs:

- `brain_mask.nii.gz` for `brain`.
- `brain.nii.gz` for `brain`, generated by masking `T1.nii.gz` when `fslmaths` is available.
- `wm.nii.gz` for `wm`.

When `-model_dir` is omitted through `primx`, the default is `modules/primx_seg/models`.

## `ACPC_Alignment.sh`

### Purpose

Run a rigid AC-PC alignment after brain extraction and before WM segmentation.

Workflow:

1. Back up original `T1.nii.gz`, `brain_mask.nii.gz`, and optional `wm.nii.gz`.
2. Crop field of view with `robustfov`.
3. Register cropped brain to a species template or custom reference with 6-DOF FLIRT.
4. Combine transforms into `ACPCAlignment/acpc.mat`.
5. Apply the transform to T1 and masks.

### Usage

```shell
bash ACPC_Alignment.sh \
  -out_path <out_path> \
  [-brainSize <mm>] \
  [-species <species> | -reference <template_brain.nii.gz>] \
  [-with_wm]
```

Options:

- `-out_path`: required. Must contain `T1.nii.gz` and `brain_mask.nii.gz`.
- `-brainSize`: `robustfov -b` radius in mm. Default: `100`.
- `-species`: case-insensitive. Built-in references are available for macaque/cynomolgus/rhesus, chimpanzee, and marmoset. If set, it overrides `-reference`.
- `-reference`: custom FLIRT reference brain image. Required when `-species` is not set.
- `-with_wm`: also transform `wm.nii.gz` when present.

Example:

```shell
singularity exec -B "$surf":"$surf" "$container" \
  "$primx" neuro acpc-align \
  -out_path "$surf/$subjid" \
  -brainSize 80 \
  -species macaque
```

## `Preprocess_3_1.sh`

### Purpose

Prepare FreeSurfer MRI volumes using DL-derived masks and species templates.

Main steps:

1. Truncate T1 intensities and create a fake-1 mm version for FreeSurfer.
2. Run `recon-all -autorecon1 -noskullstrip -notal-check`.
3. Register DL brain mask into FreeSurfer space and replace `brainmask.mgz`.
4. Generate `talairach.lta` and a GCA-normalized T1 volume.
5. For Macaque and Marmoset, nonlinearly warp the species atlas into the
   subject and use it as the primary `aseg.presurf` source. Chimpanzee instead
   runs `mri_ca_register`, `mri_ca_label`, and `mri_cc` with its own GCA.
6. Optionally build an experimental hybrid aseg that preserves warped-atlas
   subcortical anatomy while replacing cortical WM labels 2/41 with DL WM.
7. Generate `brain.mgz`, `brain.finalsurfs.mgz`, and `wm.mgz` from the selected
   final aseg.

The hybrid aseg step can change the white surface and is enabled by default.
It applies only to Macaque and Marmoset; either hybrid flag is intentionally
ignored for Chimpanzee. The Chimpanzee route retains the GCA aseg and applies
its historical claustrum-to-putamen correction, when labels 138/139 are
present, before intensity normalization and WM construction. Thus
`brain.mgz`, `aseg.presurf.mgz`, and `wm.mgz` use the same segmentation.
For A/B testing, the pipeline retains both `aseg.presurf.atlas.mgz` and
`aseg.presurf.hybrid.mgz`. Pass `-no-hybrid-aseg` to use the pure warped atlas
as `aseg.presurf.mgz`. A voxelwise difference mask is written to
`mri/fix_wm/hybrid_aseg/atlas_vs_hybrid.changed_mask.nii.gz`.

### Usage

```shell
bash Preprocess_3_1.sh \
  -id <SUB_ID> \
  -out_path <out_path> \
  [-species <species>] \
  [-hybrid-aseg|-no-hybrid-aseg] \
  [-threads <N>]
```

Inputs expected in `<out_path>`:

- `T1.nii.gz`
- `brain_mask.nii.gz`
- optional `wm.nii.gz`
- an existing `<out_path>/tmp` directory

Example:

```shell
singularity exec -B "$surf":"$surf" \
  -B "$license":/opt/freesurfer-7.2.0/.license \
  "$container" \
  "$primx" neuro preprocess-3-1 \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -species macaque
```

Pure-atlas comparison run:

```shell
primx neuro preprocess-3 \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -species marmoset \
  -no-hybrid-aseg
```

## `Preprocess_3_2.sh`

### Purpose

Build cortical surfaces after `Preprocess_3_1.sh`.

Main steps:

1. Derive an explicit central corpus-callosum seed from aseg label 253, pass
   it to `mri_fill`, and create initial `lh/rh.orig.nofix`. The script stops
   with an error if the seed label is absent.
2. Smooth, inflate, generate qsphere, and run topology fix.
3. Generate `white.preaparc`, `smoothwm`, inflated surfaces, and curvature.
4. Register spheres to the species curvature template.
5. Generate FreeSurfer annotations `aparc` and `aparc.a2009s`.
6. Generate `pial`, final white, cortical ribbon, and WM/GM surface samples.

For Marmoset only, step 6 calls
`pyscript/MarmosetPialRefinement.sh`. This T1-only refinement:

1. Retains the previous `brain.finalsurfs` result as
   `lh/rh.white.default` and `lh/rh.pial.default`, and promotes only
   `white.default` as the unchanged final white surface.
2. Creates a pial-specific N4-corrected T1. The eroded DL/atlas WM core
   weights the N4 bias-field fit, while the whole-brain mask defines the
   corrected output region; the robust WM median is then normalized to 110.
   The initial B-spline spacing of 50 is an empirical PrimateX value, not an
   NHPPipelines species parameter.
3. Generates `pial.pre_graynorm` with the dedicated Marmoset
   `-variablesigma 8 -psigma 10 -max 20` settings, `-mode 0`, and
   `-erase_cerebellum` so aseg labels 7/8/46/47 cannot attract the cerebral
   pial surface.
4. Estimates a clamped local cortical-GM correction field from that
   candidate's ribbon and generates `pial.greynorm`.
5. Promotes `pial.greynorm` to the canonical `pial` only after basic
   vertex-count and self-intersection QC succeeds.

The Marmoset-only intermediate volumes and `qc_summary.tsv` are saved in
`mri/marmoset_pial/`. The QC table records WM seed/core voxel counts,
`n4_weight_image=wm_core`, N4 intensity scaling, GM correction statistics,
and candidate surface-intersection checks. The three pial candidates remain
in `surf/` for direct visual comparison. This workflow does not require T2w
data and does not change the Macaque or Chimpanzee pial branches. Visual QC
against the T1 boundary remains required; the automatic checks only reject
structurally invalid candidate surfaces.

### Usage

```shell
bash Preprocess_3_2.sh \
  -id <SUB_ID> \
  -out_path <out_path> \
  [-species <species>] \
  [-threads <N>]
```

Both scripts use one overall `-threads N` option, with `N=1` by default.
It is passed only to commands with a confirmed explicit interface in
FreeSurfer 7.2 or ANTs: `recon-all -openmp`, `mri_em_register -threads`,
`antsRegistrationSyN.sh -n`, `mri_ca_register -threads`,
`mri_ca_label -threads`, `mris_fix_topology -threads`,
`mris_sphere -threads`, `mris_register -threads`, and
`mris_make_surfaces -openmp`. The Marmoset pial helper also constrains
`N4BiasFieldCorrection` via `ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS` (scoped to
that command invocation, not exported globally). The scripts do not set
global OpenMP or ITK thread environment variables, avoiding resource
conflicts with Slurm, GNU Parallel, and nested jobs. Other FreeSurfer commands—including
`mris_volmask` in version 7.2—FSL `flirt`/`fslmaths`, and simple conversion or
masking commands do not receive unsupported thread flags.

For example:

```shell
primx neuro preprocess-3 \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -species marmoset \
  -threads 8
```

Changing the thread count can cause very small topology-fixer differences in
some FreeSurfer releases. Keep the default `-threads 1` when exact
run-to-run reproducibility is required.

Example:

```shell
singularity exec -B "$surf":"$surf" \
  -B "$license":/opt/freesurfer-7.2.0/.license \
  "$container" \
  "$primx" neuro preprocess-3-2 \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -species macaque
```

## `Rescale.sh`

### Purpose

Convert fake-1 mm FreeSurfer outputs back to species-native voxel size.

Current native sizes:

- Macaque/cynomolgus/rhesus: 0.5 mm.
- Chimpanzee: 0.8 mm.
- Marmoset: 0.2 mm.

Main steps:

1. Rename `<out_path>/<SUB_ID>` to `<out_path>/<SUB_ID>_1mm`.
2. Create a new `<out_path>/<SUB_ID>` subject folder.
3. Rescale key MRI volumes: `rawavg`, `orig`, `brain.finalsurfs`, `brainmask`, `wm`, `aseg.presurf`.
4. Rescale `white`, `smoothwm`, and `pial` surfaces with `mri_surf2surf` using `template/fs_xfms/<Species>_rescale.dat`.
5. Copy spheres, curvature, sulc, and labels.
6. Recompute thickness and anatomical stats.

The current `mri_surf2surf` call uses the FreeSurfer 7.x-compatible form:

```shell
--reg-inv <rescale.dat> <new brain.finalsurfs.mgz> --tval-xyz <out_path>/T1.nii.gz
```

### Usage

```shell
bash Rescale.sh \
  -id <SUB_ID> \
  -out_path <out_path> \
  [-species|--species <species>]
```

Example:

```shell
singularity exec -B "$surf":"$surf" \
  -B "$license":/opt/freesurfer-7.2.0/.license \
  "$container" \
  "$primx" neuro rescale \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -species macaque
```

## `Freesurfer2CaretandRegister.sh`

### Purpose

Convert native FreeSurfer outputs to Workbench GIFTI/CIFTI and register to fs_LR meshes.

Main outputs:

- Native GIFTI surfaces, metrics, labels under `HCP_Style_Dir/Native`.
- 164k fs_LR outputs under `HCP_Style_Dir/`.
- Low-resolution fs_LR outputs under `HCP_Style_Dir/fsaverage_LR<LowResMesh>k`.
- Dense scalar CIFTI files for sulc, curvature, thickness, and areal distortion.
- Dense label CIFTI files for available parcellations.

### Usage

```shell
bash Freesurfer2CaretandRegister.sh \
  -id <SUB_ID> \
  -out_path <out_path> \
  [-LowResMesh <k>] \
  [-InflateExtraScale <scale>] \
  [-species|--species <species>] \
  [-msmsulc]
```

Options:

- `-LowResMesh`: low-resolution fs_LR mesh size in k vertices. Default: `32`.
- `-InflateExtraScale`: multiplier for generated inflated surfaces. Default: `1`.
- `-species` / `--species`: case-insensitive; `cynomolgus` and `rhesus` map to Macaque.
- `-msmsulc`: run MSM sulcal registration and use the MSMSulc sphere for resampling. Requires `msm` and bundled configs in `MSMConfig/`.

Example:

```shell
singularity exec -B "$surf":"$surf" \
  -B "$license":/opt/freesurfer-7.2.0/.license \
  "$container" \
  "$primx" neuro freesurfer2caret \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -LowResMesh 32 \
  -species macaque \
  -msmsulc
```

## `LabelResample.sh`

### Purpose

Resample left/right fs_LR label GIFTI files to the subject native mesh, convert them to FreeSurfer `.annot`, and generate anatomical stats.

This is useful when applying an external atlas or parcellation in fs_LR space back to a subject's native FreeSurfer space.

### Usage

```shell
bash LabelResample.sh \
  -id <SUB_ID> \
  -out_path <out_path> \
  -left_label <LEFT.label.gii> \
  -right_label <RIGHT.label.gii> \
  [-output_name <name>] \
  [-species <Macaque|Chimpanzee|Marmoset>] \
  [-resolution <10|32|164>] \
  [-msmsulc]
```

Options:

- `-left_label`, `-right_label`: required `.gii` label files.
- `-output_name`: FreeSurfer annotation/stats suffix. Default: `Output`.
- `-species`: currently case-sensitive. Default: `Macaque`.
- `-resolution`: source fs_LR mesh resolution in k. Default: `32`.
- `-msmsulc`: use `sphere.MSMSulc.native.surf.gii` as the target sphere. Use this only if `Freesurfer2CaretandRegister.sh -msmsulc` has been run.

Outputs:

- `<out_path>/<SUB_ID>/label/lh.<output_name>.annot`
- `<out_path>/<SUB_ID>/label/rh.<output_name>.annot`
- `<out_path>/<SUB_ID>/stats/lh.<output_name>.stats`
- `<out_path>/<SUB_ID>/stats/rh.<output_name>.stats`

Example:

```shell
singularity exec -B "$surf":"$surf" "$container" \
  "$primx" neuro label-resample \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -left_label my_atlas.L.32k_fs_LR.label.gii \
  -right_label my_atlas.R.32k_fs_LR.label.gii \
  -output_name my_atlas \
  -species Macaque \
  -resolution 32 \
  -msmsulc
```

## `Image_Reorient.py`

### Purpose

Reorient an image between explicit axis-code conventions.

### Usage

```shell
python Image_Reorient.py <input> <output> <init_axcodes> <final_axcodes>
```

Example:

```shell
singularity exec -B "$surf":"$surf" "$container" \
  "$primx" neuro image-reorient \
  "$surf/$subjid/raw_T1.nii.gz" \
  "$surf/$subjid/T1/0.nii.gz" \
  LPI LSP
```

## End-to-End Example

```shell
#!/usr/bin/env bash
set -euo pipefail

repo=/path/to/PrimateX
surf=/path/to/workdir
container=/path/to/PrimateX.sif
license=/path/to/freesurfer/license.txt
subjid=YY_T1
primx="$repo/workflows/primx_cli/primx"

# 1. T1 preprocessing
singularity exec -B "$surf":"$surf" "$container" \
  "$primx" neuro preprocess-1 \
  -t1_path "$surf/$subjid/T1" \
  -out_path "$surf/$subjid" \
  -species macaque \
  -denoise

# 2. Brain mask and ACPC alignment
singularity exec --nv -B "$surf":"$surf" "$container" \
  "$primx" seg brain \
  -species cynomolgus \
  -input_image "$surf/$subjid/T1.nii.gz" \
  -output_dir "$surf/$subjid"

singularity exec -B "$surf":"$surf" "$container" \
  "$primx" neuro acpc-align \
  -out_path "$surf/$subjid" \
  -brainSize 80 \
  -species macaque

# 3. White-matter segmentation
singularity exec --nv -B "$surf":"$surf" "$container" \
  "$primx" seg wm \
  -species cynomolgus \
  -input_image "$surf/$subjid/brain.nii.gz" \
  -output_dir "$surf/$subjid"

# 4. FreeSurfer reconstruction
singularity exec -B "$surf":"$surf" \
  -B "$license":/opt/freesurfer-7.2.0/.license \
  "$container" \
  "$primx" neuro preprocess-3 \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -species macaque

# 5. Rescale and convert/register to fs_LR
singularity exec -B "$surf":"$surf" \
  -B "$license":/opt/freesurfer-7.2.0/.license \
  "$container" \
  "$primx" neuro rescale \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -species macaque

singularity exec -B "$surf":"$surf" \
  -B "$license":/opt/freesurfer-7.2.0/.license \
  "$container" \
  "$primx" neuro freesurfer2caret \
  -id "$subjid" \
  -out_path "$surf/$subjid" \
  -LowResMesh 32 \
  -species macaque \
  -msmsulc
```

## Included Software

Typical container software includes:

| Software | Version |
| --- | --- |
| Python | 3.7.13 / 3.9.12 |
| PyTorch | 1.13.1 / 2.4.1 |
| nibabel | 4.0.2 |
| FSL | 6.0.3 |
| ANTs | 2.4.3 |
| MRtrix3 | 3.0.2 |
| FreeSurfer | 7.2.0 |
| Connectome Workbench | 1.5.0 |

## References

- Isensee et al., nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation, 2021, Nature Methods.
- Wang et al., U-net model for brain extraction: Trained on humans for transfer to non-human primates, 2021, NeuroImage.
- Glasser et al., The minimal preprocessing pipelines for the Human Connectome Project, 2013, NeuroImage.
- Markov et al., A Weighted and Directed Interareal Connectivity Matrix for Macaque Cerebral Cortex, 2014, Cerebral Cortex.
- Autio et al., Towards HCP-Style macaque connectomes: 24-Channel 3T multi-array coil, MRI sequences and preprocessing, 2020, NeuroImage.
- Donahue et al., Using diffusion tractography to predict cortical connection strength and distance: A quantitative comparison with tracers in the monkey, 2016, Journal of Neuroscience.
- Donahue et al., Quantitative assessment of prefrontal cortex in humans relative to nonhuman primates, 2018, PNAS.
- Van et al., Cortical parcellations of the Macaque monkey analyzed on surface-based atlases, 2012, Cerebral Cortex.
- Lv et al., Normative Analysis of Individual Brain Differences Based on a Population MRI-Based Atlas of Cynomolgus Macaques, 2021, Cerebral Cortex.
- https://balsa.wustl.edu/reference/976nz
- https://github.com/Washington-University/HCPpipelines
- https://github.com/Washington-University/NHPPipelines
- https://github.com/DCAN-Labs/nhp-abcd-bids-pipeline
- https://github.com/neurabenn/precon_all
- https://github.com/pGarciaS/PREEMACS

## Notes

- A FreeSurfer license is required for FreeSurfer tools. Register at https://surfer.nmr.mgh.harvard.edu/registration.html.
- Cite the relevant upstream tools and methods when using this pipeline.
- This README reflects the current script interfaces as of 2026-07-31.
