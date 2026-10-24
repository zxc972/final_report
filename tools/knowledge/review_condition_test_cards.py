"""Source-scope review before blind annotation; never reads algorithm outputs.

Edits only complete truncated quotations or narrow a statement to its cited
source. Original cards and every change are preserved. No condition labels.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.knowledge import prepare_condition_test_cards as cards
from tools.knowledge import run_condition_canonicalization as base

# method, field, 1-based index, supported statement (None = retain), exact quote
EDITS = [
    (
        "independent_fastsurfer",
        "inputs",
        1,
        None,
        "--t1 <t1_path> T1 full head input (not bias corrected). Requires an\nABSOLUTE Path!",
    ),
    (
        "independent_fastsurfer",
        "inputs",
        2,
        "Optional T2 full-head input must be externally biasfield corrected when --no_biasfield is used.",
        "*Optional* T2 full head input (must be externally biasfield\ncorrected when called with --no_biasfield). Requires an\nABSOLUTE Path!",
    ),
    (
        "independent_fastsurfer",
        "inputs",
        3,
        "An optional binary lesion mask must be in the same space as the T1 input.",
        None,
    ),
    (
        "independent_fastsurfer",
        "inputs",
        4,
        None,
        "--surf_only: Only run the surface pipeline. The segmentation created by FastSurferVINN must already exist in this case.",
    ),
    (
        "independent_fastsurfer",
        "conditions",
        1,
        "A segmentation without --tal_reg does not need a FreeSurfer licence.",
        None,
    ),
    (
        "independent_fastsurfer",
        "conditions",
        2,
        "Docker runs of the surface module require --fs_license pointing to a FreeSurfer licence file.",
        "Required for Docker when running surface module:\n\n--fs_license: Path to FreeSurfer license key file",
    ),
    (
        "independent_fastsurfer",
        "conditions",
        3,
        "Input conformation specifications are checked automatically; non-compliant images are conformed.",
        None,
    ),
    (
        "independent_fastsurfer",
        "conditions",
        4,
        "Keeping native image geometry is incompatible with the surface pipeline.",
        "Output all images and segmentations in the native\n--keepgeom image space with its image geometry (voxel size,\ndimensions, orientation). This setting is not\ncompatible with the surface pipeline",
    ),
    (
        "independent_fastsurfer",
        "conditions",
        5,
        "A GPU makes segmentation much faster.",
        None,
    ),
    (
        "independent_fastsurfer",
        "steps",
        1,
        "run_fastsurfer.sh is called once for each T1w MRI image to be processed.",
        None,
    ),
    (
        "independent_fastsurfer",
        "steps",
        3,
        None,
        "a segmentation using FastSurferVINN (equivalent to FreeSurfer\naparc.DKTatlas+aseg.mgz)",
    ),
    (
        "independent_fastsurfer",
        "checks",
        2,
        None,
        "--ignore_fs_version Switch on to avoid check for FreeSurfer version.\nProgram will terminate if the supported version\n(see recon-surf.sh) is not sourced.",
    ),
    (
        "independent_fastsurfer",
        "outputs",
        4,
        "The cerebellum module adds a sub-segmentation image and a summary-statistics text file.",
        None,
    ),
    (
        "independent_fastsurfer",
        "parameters",
        1,
        "With --vox_size min (default), voxel size is read from the smallest per-direction voxel size in the T1w image.",
        'If "min" is specified (default), the voxel size is\nread from the size of the minimal voxel size\n(smallest per-direction voxel size) in the T1w\nimage:',
    ),
    (
        "independent_fastsurfer",
        "parameters",
        3,
        "--3T uses the 3T atlas instead of the 1.5T atlas for Talairach registration.",
        None,
    ),
    (
        "independent_fs_glmfit_group",
        "inputs",
        1,
        "The input data file has each frame as a separate input.",
        None,
    ),
    (
        "independent_fs_glmfit_group",
        "inputs",
        4,
        "Surface-based smoothing requires --surf; otherwise the input is treated as a volume.",
        None,
    ),
    (
        "independent_fs_glmfit_group",
        "conditions",
        1,
        None,
        "Resampling each subject's data into a common space.\n\nConcatenating all the subjects' into a single file.",
    ),
    (
        "independent_fs_glmfit_group",
        "conditions",
        4,
        "If data have not been cached, the same operations can be performed manually.",
        None,
    ),
    (
        "independent_fs_glmfit_group",
        "steps",
        2,
        "The tutorial contrast has one value for each parameter (four values in its example).",
        "There is one value for each parameter (so 4 values).",
    ),
    (
        "independent_fs_glmfit_group",
        "steps",
        3,
        "Assemble previously cached data using mris_preproc with the FSGD, target fsaverage, hemisphere, and output file.",
        "mris_preproc --fsgd gender_age.fsgd \\\n--cache-in thickness.fwhm10.fsaverage \\\n--target fsaverage \\\n--hemi lh \\\n--out lh.gender_age.thickness.10.mgh",
    ),
    (
        "independent_fs_glmfit_group",
        "checks",
        1,
        "The completed GLM has its output subdirectory under the glm directory.",
        None,
    ),
    (
        "independent_fs_glmfit_group",
        "checks",
        2,
        None,
        "There will be a subdirectory for each contrast that you specify. The name of the directory will be that of the contrast matrix file (without the .mtx extension).",
    ),
    (
        "independent_fs_glmfit_group",
        "exceptions",
        3,
        None,
        "Do not use with --sim. Rather, run the non-sim analysis with --prune, then pass the created mask when running simulation.",
    ),
    (
        "independent_fs_glmfit_group",
        "parameters",
        1,
        "Spatial smoothing can be performed between resampling subjects into common space and concatenating their data.",
        "Resampling each subject's data into a common space.\n\nConcatenating all the subjects' into a single file.\n\nSpatial smoothing (can be done between 1 and 2).",
    ),
    (
        "independent_nmt_v2_charm",
        "inputs",
        1,
        None,
        "The CHARM is distributed with the NMT v2. The NMT v2 has several forms\nand variants (based on symmetry/asymmetry, FOV and voxel size), and\nfor each of these there is an accompanying CHARM.",
    ),
    (
        "independent_nmt_v2_charm",
        "conditions",
        2,
        None,
        "The NMT v2 has several forms\nand variants (based on symmetry/asymmetry, FOV and voxel size), and\nfor each of these there is an accompanying CHARM.",
    ),
    (
        "independent_nmt_v2_charm",
        "exceptions",
        2,
        None,
        'CHARM Level 1 is volume "[0]" and Level 6 is volume\n"[5]", because AFNI (like Python and C) use zero-base counting.',
    ),
    (
        "independent_nmt_v2_charm",
        "parameters",
        3,
        None,
        'Specify the desired variant SS as either "sym" or\n"asym". Option is valid for the NMT v2 only--in\nother cases it is ignored. (default = "sym")',
    ),
    (
        "independent_workbench_area_stats",
        "inputs",
        3,
        None,
        "[-roi] - only consider data inside an roi\n<roi-metric> - the roi, as a metric file",
    ),
    (
        "independent_workbench_area_stats",
        "conditions",
        3,
        "The reduction operation must be selected from the documented allowed list.",
        None,
    ),
    (
        "independent_workbench_area_stats",
        "outputs",
        4,
        None,
        "If the -roi option is used without\n-match-maps, then each line will contain as many numbers as there are\nmaps in the ROI file, separated by tab characters.",
    ),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    out = Path(ap.parse_args().out)
    originals = out / "source_review/original_cards"
    originals.mkdir(parents=True, exist_ok=False)
    changed = []
    all_cards = {}
    for method in cards.METHODS:
        path = out / "method_extractions" / (method["method_id"] + ".json")
        (originals / path.name).write_bytes(path.read_bytes())
        all_cards[method["method_id"]] = json.loads(path.read_text(encoding="utf-8"))
    for method, field, index, statement, quote in EDITS:
        claim = all_cards[method][field][index - 1]
        before = dict(claim)
        if statement is not None:
            claim["statement"] = statement
        if quote is not None:
            claim["quote"] = quote
        text = (out / "sources" / (claim["source_id"] + ".txt")).read_text(
            encoding="utf-8"
        )
        assert 8 <= len(claim["quote"]) <= 250, (
            method,
            field,
            index,
            len(claim["quote"]),
        )
        assert claim["quote"] in text, (method, field, index, claim["quote"])
        start = text.index(claim["quote"])
        claim["source_span"] = {
            "start": start,
            "end": start + len(claim["quote"]),
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
        changed.append(
            {
                "method": method,
                "field": field,
                "index": index,
                "before": before,
                "after": dict(claim),
                "reason": "complete exact quotation or narrow statement to cited source; no condition label assigned",
            }
        )
    for method in cards.METHODS:
        card = all_cards[method["method_id"]]
        texts = {
            sid: (out / "sources" / (sid + ".txt")).read_text(encoding="utf-8")
            for sid in method["sources"]
        }
        card, good, bad = cards.validate_card(card, method, texts)
        assert not bad
        card["evidence_status"] = (
            "exact_quotes_verified_agent_scope_reviewed_blind_gold_pending"
        )
        base.save_json(
            out / "method_extractions" / (method["method_id"] + ".json"), card
        )
    base.save_json(
        out / "source_review/review_audit.json",
        {
            "reviewer": "Codex source-scope check, not expert gold annotation",
            "screened_statements": sum(
                sum(len(v[f]) for f in cards.FIELDS) for v in all_cards.values()
            ),
            "changed_items": len(changed),
            "edits": changed,
            "algorithm_outputs_read": False,
            "gold_labels_created": False,
        },
    )
    cards.prepare_annotation(out)
    base.save_json(
        out / "source_review/frozen.json",
        {
            "script_sha256": base.sha256(__file__),
            "review_audit_sha256": base.sha256(out / "source_review/review_audit.json"),
            "handoff_manifest_sha256": base.sha256(
                out / "claude_annotation_packet/HANDOFF_MANIFEST.json"
            ),
            "annotation_frozen": False,
            "freeze_type": "source_cards_only",
        },
    )
    print("SOURCE_SCOPE_REVIEWED", len(changed))


if __name__ == "__main__":
    main()
