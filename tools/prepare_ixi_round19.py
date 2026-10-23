"""Source-bound IXI20 demographics and explicit QC declarations; no image changes."""

import csv
import datetime as dt
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import sys

ROOT = Path("/data/xuancheng/datasets")
AUDIT = ROOT / "provenance/round19_ixi_group_20261023"
TRIAL = Path("/data/xuancheng/agent_v1/retests/round19_20261023")
SUBJECTS = [
    "IXI064",
    "IXI294",
    "IXI307",
    "IXI045",
    "IXI625",
    "IXI353",
    "IXI445",
    "IXI434",
    "IXI216",
    "IXI288",
    "IXI095",
    "IXI303",
    "IXI026",
    "IXI267",
    "IXI542",
    "IXI198",
    "IXI546",
    "IXI442",
    "IXI158",
    "IXI327",
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, text):
    temporary = path.with_name(path.name + ".round19.tmp")
    with temporary.open("x", encoding="utf-8", newline="") as stream:
        stream.write(text)
    temporary.replace(path)


def main():
    if (AUDIT / "data_registration.json").exists():
        raise SystemExit("Already registered; inspect instead of repeating")
    sys.path.insert(0, str(AUDIT / "python_dependencies"))
    import xlrd

    manifest = json.loads((ROOT / "manifest_IXI.json").read_text())
    selected = {
        row["subject_id"]: row for row in manifest if row["subject_id"] in SUBJECTS
    }
    assert set(selected) == set(SUBJECTS)
    assert all(row["held_out"] is False for row in selected.values())
    assert all(row["preprocessing_status"] == "completed" for row in selected.values())
    untouched = {
        row["subject_id"]: dict(row)
        for row in manifest
        if row["subject_id"] not in SUBJECTS
    }
    visual_path = AUDIT / "claude_visual_review_source.csv"
    with visual_path.open(encoding="utf-8-sig", newline="") as stream:
        visual_rows = list(csv.DictReader(stream))
    visual = {row["subject"]: row for row in visual_rows}
    assert len(visual_rows) == 20 and set(visual) == set(SUBJECTS)
    assert {
        sid for sid, row in visual.items() if row["visual_verdict"] == "需复核"
    } == {"IXI303", "IXI542"}
    auto_path = (
        ROOT
        / "provenance/macaque_global_acceptance_20261023/ixi_auto_qc/IXI20_automatic_qc.json"
    )
    auto = {row["subject"]: row for row in json.loads(auto_path.read_text())["rows"]}
    assert set(auto) == set(SUBJECTS)
    added = [
        "qc_visual",
        "qc_note",
        "qc_reviewer",
        "qc_visual_source",
        "qc_auto_source",
        "qc_automatic_flags",
    ]
    metric_map = {
        "qc_euler_lh_orig_nofix": "lh_euler_orig_nofix",
        "qc_euler_rh_orig_nofix": "rh_euler_orig_nofix",
        "qc_euler_lh_white": "lh_euler_white",
        "qc_euler_rh_white": "rh_euler_white",
        "qc_mean_thickness_mm": "mean_thickness_mm",
        "qc_total_area_mm2": "total_area_mm2",
        "qc_etiv_mm3": "etiv_mm3",
    }
    added.extend(metric_map)
    for sid in SUBJECTS:
        row, review, metrics = selected[sid], visual[sid], auto[sid]
        notes = [review["finding_locations"], review["followup_needed"]]
        if review["visual_verdict"] == "需复核":
            notes.append(
                "低对比与局部 pial 边界待复核；本次保留，报告须披露，不作专家验收声明"
            )
        if metrics["needs_review"]:
            notes.append("自动 3 MAD 标记保留，不剔除；筛查提示不是病理判断")
        row.update(
            qc_visual=review["visual_verdict"],
            qc_note="；".join(notes),
            qc_reviewer="Claude AI 初查，非专家盲审",
            qc_visual_source=str(visual_path),
            qc_auto_source=str(auto_path),
            qc_automatic_flags=json.dumps(metrics["flags"], ensure_ascii=False),
        )
        row.update({target: metrics[source] for target, source in metric_map.items()})
    assert all(
        row == untouched[row["subject_id"]]
        for row in manifest
        if row["subject_id"] not in SUBJECTS
    )
    xls_path = ROOT / "raw/IXI/IXI.xls"
    sheet = xlrd.open_workbook(str(xls_path)).sheet_by_name("Table")
    headers = sheet.row_values(0)
    columns = {
        name: headers.index(name) for name in ["IXI_ID", "AGE", "SEX_ID (1=m, 2=f)"]
    }
    population, source_rows = {}, {}
    for index in range(1, sheet.nrows):
        identifier = sheet.cell_value(index, columns["IXI_ID"])
        if not isinstance(identifier, (int, float)) or not math.isfinite(identifier):
            continue
        sid = f"IXI{int(identifier):03d}"
        if sid not in selected:
            continue
        assert sid not in population
        value = sheet.cell_value(index, columns["AGE"])
        age = (
            float(value)
            if isinstance(value, (int, float)) and math.isfinite(value)
            else None
        )
        value = sheet.cell_value(index, columns["SEX_ID (1=m, 2=f)"])
        if value in ("", None):
            sex = ""
        elif value in (1, 2):
            sex = {1: "M", 2: "F"}[value]
        else:
            raise ValueError("Unexpected sex code: " + sid)
        row = selected[sid]
        assert age is None or abs(age - float(row["age"])) < 1e-10
        assert sex == (row["sex"] or "")
        population[sid] = {
            "participant_id": sid,
            "age": "" if age is None else repr(age),
            "sex": sex,
            "site": row["site"],
            "field_strength": row["scanner_field_strength"],
        }
        source_rows[sid] = index + 1
    assert set(population) == set(SUBJECTS)
    required = [
        f"{directory}/{hemi}.{suffix}"
        for hemi in ["lh", "rh"]
        for directory, suffix in [
            ("surf", "white"),
            ("surf", "pial"),
            ("surf", "thickness"),
            ("label", "aparc.DKTatlas.annot"),
            ("label", "cortex.label"),
        ]
    ]
    for sid in SUBJECTS:
        root = ROOT / "slim/IXI" / sid
        for rel in required:
            path = root / rel
            assert path.is_file() and path.resolve().is_relative_to(root), str(path)
    table_dir = ROOT / "participants/IXI20_20261023"
    table_dir.mkdir(parents=True)
    table_path = table_dir / "participants.tsv"
    with table_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["participant_id", "age", "sex", "site", "field_strength"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(population[sid] for sid in SUBJECTS)
    catalogue = {
        "roots": [],
        "participants_tables": [
            {
                "dataset": "IXI",
                "path": str(table_path),
                "id_column": "participant_id",
                "source": "IXI.xls, Table: IXI_ID / AGE / SEX_ID (1=m, 2=f); site and field strength from official IXI descriptions",
                "license": "CC BY-SA 3.0",
            }
        ],
    }
    for sid in SUBJECTS:
        row = selected[sid]
        catalogue["roots"].append(
            {
                "path": str(ROOT / "slim/IXI" / sid),
                "subject_id": sid,
                "species_declared": "human",
                "species_verified": "declared_by_IXI_dataset",
                "dataset": "IXI",
                "license": "CC BY-SA 3.0",
                "source": "https://brain-development.org/ixi-dataset/",
                "original_derivative_root": str(
                    ROOT / "derivatives/primatex_1.7" / sid
                ),
                **{key: row[key] for key in added},
            }
        )
    before = {}
    for filename in ["manifest_IXI.json", "manifest_IXI.csv"]:
        backup = AUDIT / (filename + ".before")
        assert not backup.exists()
        shutil.copyfile(ROOT / filename, backup)
        before[filename] = sha(backup)
    with (AUDIT / "manifest_IXI.csv.before").open(
        encoding="utf-8-sig", newline=""
    ) as stream:
        reader = csv.DictReader(stream)
        fields = list(reader.fieldnames)
        csv_rows = list(reader)
    fields.extend(key for key in added if key not in fields)
    for row in csv_rows:
        if row["subject_id"] in selected:
            row.update({key: selected[row["subject_id"]][key] for key in added})
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(csv_rows)
    atomic(
        ROOT / "manifest_IXI.json",
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    atomic(ROOT / "manifest_IXI.csv", buffer.getvalue())
    catalog_path = TRIAL / "catalog.ixi20.json"
    catalog_path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n")
    record = {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "subjects": SUBJECTS,
        "n": 20,
        "source_xls": {
            "path": str(xls_path),
            "sha256": sha(xls_path),
            "reader": "xlrd 2.0.2",
            "sheet": "Table",
            "columns": columns,
            "row_numbers_1based": source_rows,
        },
        "participants_table": {
            "path": str(table_path),
            "sha256": sha(table_path),
            "missing_age": sum(not population[s]["age"] for s in SUBJECTS),
            "missing_sex": sum(not population[s]["sex"] for s in SUBJECTS),
        },
        "visual_source_sha256": sha(visual_path),
        "auto_source_sha256": sha(auto_path),
        "manifest_before": before,
        "manifest_after": {p: sha(ROOT / p) for p in before},
        "catalogue": {"path": str(catalog_path), "sha256": sha(catalog_path)},
        "required_inputs_per_subject": required,
        "review_pending_retained": ["IXI303", "IXI542"],
        "automatic_flag_retained": ["IXI442"],
        "no_qc_exclusions": True,
        "noncohort_manifest_values_unchanged": True,
        "raw_or_derivative_data_modified": False,
        "model_api_requests": 0,
    }
    with (AUDIT / "data_registration.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                key: record[key]
                for key in [
                    "n",
                    "participants_table",
                    "catalogue",
                    "review_pending_retained",
                    "model_api_requests",
                ]
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
