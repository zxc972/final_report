PrimateX Segmentation Module
============================

This module provides nnU-Net-based brain extraction and white-matter
segmentation, plus a small image router that predicts species and whether the
input contains scalp or is already brain-extracted.

Preferred interface
-------------------

Run segmentation through the repository-level `primx` CLI:

    primx=/path/to/PrimateX/workflows/primx_cli/primx

    "$primx" seg brain \
        -species cynomolgus \
        -input_image /path/to/T1.nii.gz \
        -output_dir /path/to/subject

    "$primx" seg wm \
        -species cynomolgus \
        -input_image /path/to/subject/brain.nii.gz \
        -output_dir /path/to/subject

`primx seg brain|wm` supplies
`modules/primx_seg/models` as `-model_dir` when that argument is omitted.
The current segmentation predictor constructs a CUDA device, so expose an
NVIDIA GPU with `--nv` when running inside Singularity/Apptainer. The router
itself can fall back to CPU.

Inputs and model layout
-----------------------

`Inference.py` accepts:

    -species       rhesus | cynomolgus | chimpanzee | marmoset | human
    -task          brain | wm
    -input_image   one .nii or .nii.gz image
    -output_dir    output directory
    -model_dir     model root containing <species>_<task>/ directories
    -code_path     optional nnU-Net v2 source path
    --device_id    CUDA device index (default: 0)

Examples of expected model directories are:

    models/cynomolgus_brain/
    models/cynomolgus_wm/
    models/marmoset_brain/
    models/marmoset_wm/

Each selected directory must contain a discoverable trained checkpoint and
its nnU-Net metadata. Only installed species/task combinations can run.

Outputs
-------

Brain extraction writes:

    brain_mask.nii.gz
    Seg_Skull_Stripping_QC.txt

The `primx seg brain` wrapper also writes `brain.nii.gz` by masking the input
with `brain_mask.nii.gz` when `fslmaths` is available. If `fslmaths` is not
available, the mask and QC file are still retained and the wrapper prints a
warning.

White-matter segmentation writes:

    wm.nii.gz
    Seg_WM_QC.txt

The QC text files contain entropy summaries and connected-component counts.
They are screening information, not a substitute for visual QC.

Direct Python interface
-----------------------

The underlying entrypoint can also be called directly:

    python modules/primx_seg/Inference.py \
        -species marmoset \
        -task wm \
        -input_image /path/to/brain.nii.gz \
        -output_dir /path/to/subject \
        -model_dir /path/to/models \
        --device_id 0

Direct `Inference.py -task brain` does not perform the wrapper's additional
`fslmaths` step that creates `brain.nii.gz`.

Species and image router
------------------------

Use the router when the species or input image type is unknown:

    "$primx" seg router -input_image /path/to/T1.nii.gz

It returns JSON:

    {
      "species": "marmoset",
      "imageType": "scalp"
    }

Possible species labels are `marmoset`, `cynomolgus monkey`, `chimpanzee`,
`rhesus monkey`, and `human`; image type is `scalp` or `brain`. Treat the
prediction as a routing suggestion and confirm it before launching a
species-specific pipeline. For the segmentation CLI, map `cynomolgus monkey`
to `cynomolgus` and `rhesus monkey` to `rhesus`.
