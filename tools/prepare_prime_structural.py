"""Extract explicitly approved PRIME-DE structural files and build a sourced manifest.

No preprocessing, account registration, credential handling, or species guessing.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_participants(path, subjects, held_out=()):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    mapped = {row["Subject ID"].strip(): row for row in rows}
    if len(mapped) != len(rows):
        raise ValueError("Duplicate participant identifiers")
    if len(set(subjects)) != len(subjects) or not 1 <= len(subjects) <= 32:
        raise ValueError("Select 1..32 distinct, explicitly approved subjects")
    excluded = set(map(str, held_out)) | {"102311", "105216"}
    selected = []
    for subject in subjects:
        if subject in excluded:
            raise ValueError("Held-out subject is forbidden")
        if subject not in mapped or not subject.isdigit():
            raise ValueError(
                "Subject must occur exactly in the official participant table"
            )
        row = mapped[subject]
        if row["Species"].strip() != "Macaca mulatta":
            raise ValueError("Only individually declared Macaca mulatta are approved")
        selected.append(row)
    return selected


def extract_structural(archive, output, subjects):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise ValueError("Selected-data root must not be a symlink")
    bids = {"sub-" + subject.zfill(6): subject for subject in subjects}
    records = []
    with tarfile.open(archive, "r|gz") as stream:
        for member in stream:
            parts = PurePosixPath(member.name)
            selected = next(
                (sid for key, sid in bids.items() if key in parts.parts), None
            )
            if selected is None or "anat" not in parts.parts:
                continue
            if not member.name.endswith((".nii.gz", ".json")):
                continue
            if (
                not member.isfile()
                or parts.is_absolute()
                or ".." in parts.parts
                or not 0 <= member.size <= 1024**3
            ):
                raise ValueError("Unsafe or oversized structural archive member")
            target = output.joinpath(*parts.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if (
                not target.resolve().is_relative_to(output.resolve())
                or target.is_symlink()
            ):
                raise ValueError(
                    "Structural output escapes the selected-data directory"
                )
            source = stream.extractfile(member)
            if target.exists():
                digest = hashlib.sha256()
                for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    digest.update(chunk)
                if (
                    target.stat().st_size != member.size
                    or sha256(target) != digest.hexdigest()
                ):
                    raise ValueError(
                        "Existing raw structural file differs; refusing overwrite"
                    )
            else:
                with target.open("xb") as destination:
                    shutil.copyfileobj(source, destination)
            if target.stat().st_size != member.size:
                raise ValueError("Incomplete structural member")
            records.append(
                {
                    "subject_id": selected,
                    "path": str(target),
                    "bytes": member.size,
                    "raw_sha256": sha256(target),
                }
            )
    return records


def header_record(path):
    import nibabel as nib
    import numpy as np

    image = nib.load(str(path))
    units = image.header.get_xyzt_units()[0]
    factors = {"mm": 1.0, "meter": 1000.0, "micron": 0.001}
    zooms = [float(z) for z in image.header.get_zooms()[:3]]
    physical = [z * factors[units] for z in zooms] if units in factors else None
    q, qc = image.get_qform(coded=True)
    s, sc = image.get_sform(coded=True)
    conflict = bool(qc and sc and not np.allclose(q, s, atol=1e-5, rtol=0))
    return {
        "dims": list(image.shape),
        "voxel_size_stored": zooms,
        "voxel_size_unit": units,
        "voxel_size_mm": physical,
        "dtype": str(image.get_data_dtype()),
        "qform_code": int(qc),
        "sform_code": int(sc),
        "qform_sform_conflict": conflict,
        "orientation": list(nib.aff2axcodes(image.affine)),
        "source": {
            "path": str(path),
            "method": "NiBabel NIfTI header; no voxel statistics or resampling",
        },
    }


def build_manifest(site, participants_path, selected, files, source_url, download_url):
    rows = []
    for person in selected:
        sid = person["Subject ID"]
        candidates = sorted(
            (
                r
                for r in files
                if r["subject_id"] == sid and r["path"].endswith("_T1w.nii.gz")
            ),
            key=lambda r: r["path"],
        )
        if not candidates:
            raise ValueError("Approved subject has no complete T1w structural file")
        first = candidates[0]
        header = header_record(first["path"])
        age = person.get("Age (years)", person.get("Age (Years)", ""))
        row = {
            "subject_id": site.upper() + "_" + sid,
            "dataset": "PRIME-DE",
            "site": site,
            "source_subject_id": sid,
            "species": person["Species"],
            "species_verified": "declared_by_individual_dataset_record",
            "species_source": str(participants_path),
            "participants_sha256": sha256(participants_path),
            "age": age or None,
            "sex": person.get("Sex") or None,
            "t1_file": first["path"],
            "t1_files": [r["path"] for r in candidates],
            "header": header,
            "raw_sha256": first["raw_sha256"],
            "held_out": False,
            "preprocessing_status": "not_started",
            "scale_status": "unknown",
            "license": "CC-BY-NC-SA; official site, version not independently established",
            "source_url": source_url,
            "download_url": download_url,
            "notes": "First structural session chosen before processing; repeats do not increase independent n. Header units and nominal site resolution remain separate from physical calibration.",
        }
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", choices=["ucdavis", "ion"], required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--participants", type=Path, required=True)
    parser.add_argument("--subjects", nargs="+", required=True)
    parser.add_argument("--selected-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--held-out-json", type=Path)
    args = parser.parse_args()
    held_out = json.loads(args.held_out_json.read_text()) if args.held_out_json else []
    if isinstance(held_out, dict):
        held_out = held_out["held_out_subject_ids"]
    selected = select_participants(args.participants, args.subjects, held_out)
    if args.manifest.exists() or args.manifest.with_suffix(".csv").exists():
        raise ValueError("Manifest exists; preserve it and use a new audit path")
    files = extract_structural(args.archive, args.selected_dir, args.subjects)
    url = "https://fcon_1000.projects.nitrc.org/indi/PRIME/" + args.site + ".html"
    download = "https://www.nitrc.org/frs/downloadlink.php/" + (
        "10421" if args.site == "ucdavis" else "10571"
    )
    rows = build_manifest(args.site, args.participants, selected, files, url, download)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with args.manifest.with_suffix(".csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(
            {
                k: json.dumps(v) if isinstance(v, (list, dict)) else v
                for k, v in row.items()
            }
            for row in rows
        )
    audit = {
        "source_archive": str(args.archive),
        "archive_bytes": args.archive.stat().st_size,
        "archive_sha256": sha256(args.archive),
        "subjects": args.subjects,
        "structural_files": files,
        "preprocessing_started": False,
        "credentials_used": False,
    }
    args.manifest.with_suffix(".audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "subjects": len(rows),
                "structural_files": len(files),
                "status": "downloaded_and_catalogued",
            }
        )
    )


if __name__ == "__main__":
    main()
