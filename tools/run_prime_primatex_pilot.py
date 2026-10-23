"""Run one explicitly selected, non-held-out rhesus PrimateX pilot.

Existing services are not managed. Raw data and source are mounted read-only;
only this new pilot output is writable. No provider API or automatic retry.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import time


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def resources(pid):
    observed = subprocess.run(
        ["ps", "-eo", "pid=,ppid=,rss="], capture_output=True, text=True, check=True
    )
    rows = [
        tuple(map(int, line.split()))
        for line in observed.stdout.splitlines()
        if len(line.split()) == 3
    ]
    owned = {pid}
    while True:
        expanded = owned | {child for child, parent, _ in rows if parent in owned}
        if expanded == owned:
            break
        owned = expanded
    rss = sum(memory for child, _, memory in rows if child in owned)
    gpu = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_memory",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
    )
    memory = 0
    for line in gpu.stdout.splitlines():
        parts = line.split(",")
        if (
            len(parts) == 2
            and parts[0].strip().isdigit()
            and parts[1].strip().isdigit()
            and int(parts[0]) in owned
        ):
            memory += int(parts[1])
    return rss, memory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "manifest",
        "subject",
        "repo",
        "image",
        "config",
        "license-file",
        "output",
        "audit",
        "model-receipt",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--engine", default="/usr/local/bin/singularity")
    parser.add_argument("--through", choices=["preprocess1", "all"], default="all")
    args = parser.parse_args()
    audit, output, repo = map(Path, (args.audit, args.output, args.repo))
    rows = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
    selected = [row for row in rows if row["subject_id"] == args.subject]
    if len(selected) != 1:
        raise ValueError(
            "Subject must occur exactly once in the explicit data manifest"
        )
    row = selected[0]
    if (
        row.get("held_out") not in (False, "no", "否", "false", "0")
        or row["species"] != "Macaca mulatta"
    ):
        raise ValueError(
            "Pilot requires a non-held-out individually declared rhesus subject"
        )
    source = Path(row["t1_file"]).resolve(strict=True)
    if digest(source) != row["raw_sha256"]:
        raise ValueError("Raw input differs from its registered SHA-256")
    if (
        source.is_relative_to(output.resolve())
        or output.resolve() == output.parent.resolve()
    ):
        raise ValueError("Output must be an independent subject directory")
    if not Path(args.license_file).is_file():
        raise ValueError("Existing read-only FreeSurfer license file is required")
    audit.mkdir(parents=True, exist_ok=True)
    if (audit / "pilot_status.json").exists():
        raise ValueError(
            "Pilot state already exists; inspect it instead of starting a duplicate"
        )
    # A prior read-only preflight may have created output/tmp. Nothing else may exist.
    if output.exists() and any(item.name != "tmp" for item in output.iterdir()):
        raise ValueError("Refusing to overwrite an existing derivative")
    (output / "tmp").mkdir(parents=True, exist_ok=True)
    environment = audit / "inside_environment.sh"
    if not environment.is_file():
        raise ValueError(
            "Reviewed, source-recorded container environment script is required"
        )
    prefix = [
        args.engine,
        "--config",
        args.config,
        "exec",
        "--cleanenv",
        "--containall",
        "--no-home",
        "--net",
        "--network",
        "none",
        "--no-mount",
        "hostfs,cwd,tmp",
        "--pwd",
        "/work",
    ]
    for binding in (
        str(source) + ":/input/T1w.nii.gz:ro",
        str(repo) + ":/primatex:ro",
        str(output) + ":/work:rw",
        str(audit) + ":/provenance:ro",
        args.license_file + ":/license.txt:ro",
    ):
        prefix.extend(["--bind", binding])
    cli = "/primatex/workflows/primx_cli/primx"
    sid = args.subject
    commands = [
        (
            "preprocess1",
            False,
            [
                cli,
                "neuro",
                "preprocess-1",
                "-t1_path",
                "/input/T1w.nii.gz",
                "-out_path",
                "/work",
                "-species",
                "Macaque",
                "-denoise",
                "-tmp",
            ],
            ["T1.nii.gz"],
        ),
        (
            "brain",
            True,
            [
                cli,
                "seg",
                "brain",
                "-species",
                "rhesus",
                "-input_image",
                "/work/T1.nii.gz",
                "-output_dir",
                "/work",
            ],
            ["brain_mask.nii.gz", "brain.nii.gz"],
        ),
        (
            "acpc",
            False,
            [
                cli,
                "neuro",
                "acpc-align",
                "-out_path",
                "/work",
                "-brainSize",
                "80",
                "-species",
                "Macaque",
            ],
            ["brain.nii.gz", "T1.nii.gz"],
        ),
        (
            "wm",
            True,
            [
                cli,
                "seg",
                "wm",
                "-species",
                "rhesus",
                "-input_image",
                "/work/brain.nii.gz",
                "-output_dir",
                "/work",
            ],
            ["wm.nii.gz"],
        ),
        (
            "preprocess3_1",
            False,
            [
                cli,
                "neuro",
                "preprocess-3-1",
                "-id",
                sid,
                "-out_path",
                "/work",
                "-species",
                "Macaque",
            ],
            [sid + "/mri/wm.mgz"],
        ),
        (
            "preprocess3_2",
            False,
            [
                cli,
                "neuro",
                "preprocess-3-2",
                "-id",
                sid,
                "-out_path",
                "/work",
                "-species",
                "Macaque",
            ],
            [sid + "/surf/lh.pial", sid + "/surf/rh.pial"],
        ),
        (
            "rescale",
            False,
            [
                cli,
                "neuro",
                "rescale",
                "-id",
                sid,
                "-out_path",
                "/work",
                "-species",
                "Macaque",
            ],
            [sid + "/surf/lh.thickness", sid + "/surf/rh.thickness"],
        ),
        (
            "freesurfer2caret",
            False,
            [
                cli,
                "neuro",
                "freesurfer2caret",
                "-id",
                sid,
                "-out_path",
                "/work",
                "-LowResMesh",
                "32",
                "-species",
                "Macaque",
            ],
            [],
        ),
    ]
    planned = []
    for name, gpu, command, expected in commands:
        options = prefix[:]
        if gpu:
            options.insert(options.index("--pwd"), "--nv")
        argv = (
            options
            + [args.image, "/bin/bash", "/provenance/inside_environment.sh"]
            + command
        )
        planned.append(
            {
                "stage": name,
                "gpu_requested": gpu,
                "argv": argv,
                "expected_products": expected,
            }
        )
    plan = {
        "subject": sid,
        "input": str(source),
        "raw_sha256": row["raw_sha256"],
        "species": row["species"],
        "species_source": row["species_source"],
        "source_commit": subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip(),
        "script_sha256": digest(Path(__file__)),
        "environment_sha256": digest(environment),
        "model_receipt": args.model_receipt,
        "steps": planned,
        "threads": 4,
        "automatic_retries": 0,
        "network": "none",
        "held_out": False,
        "qc_visual_review": "pending",
        "scale_status": "unknown_until_actual_rescale_receipts_and_geometry_are_checked",
    }
    save(audit / "pilot_plan.json", plan)
    (audit / "commands.txt").write_text(
        "\n\n".join(step["stage"] + "\n" + shlex.join(step["argv"]) for step in planned)
        + "\n"
    )
    state = {
        "subject": sid,
        "pid": os.getpid(),
        "stage": "starting",
        "started_utc": utc(),
        "plan_sha256": digest(audit / "pilot_plan.json"),
        "steps": [],
        "raw_unchanged": True,
        "provider_requests": 0,
        "automatic_retries": 0,
    }
    save(audit / "pilot_status.json", state)
    model_checked = False
    for step in planned:
        name = step["stage"]
        if name == "brain" and not model_checked:
            state.update(stage="waiting_for_verified_rhesus_models")
            save(audit / "pilot_status.json", state)
            deadline = time.monotonic() + 3600
            receipt = Path(args.model_receipt)
            while not receipt.is_file() and time.monotonic() < deadline:
                time.sleep(10)
            if not receipt.is_file():
                state.update(stage="blocked_models_missing", ended_utc=utc())
                save(audit / "pilot_status.json", state)
                return 2
            installed = json.loads(receipt.read_text())
            if (
                installed.get("commit") != "ab48594a75179c0cf427c5c41aa10655ebe29c8f"
                or len(installed.get("files", [])) != 6
            ):
                raise ValueError(
                    "Model installation receipt is not the reviewed official revision"
                )
            for entry in installed["files"]:
                if (
                    entry["status"] != "verified"
                    or digest(repo / "modules/primx_seg/models" / entry["path"])
                    != entry["sha256"]
                ):
                    raise ValueError(
                        "Installed model differs from verified official content"
                    )
            model_checked = True
            state["model_receipt_sha256"] = digest(receipt)
        state.update(stage=name, updated_utc=utc())
        save(audit / "pilot_status.json", state)
        record = {
            "stage": name,
            "argv": step["argv"],
            "started_utc": utc(),
            "status": "running",
            "gpu_requested": step["gpu_requested"],
        }
        journal = audit / (name + ".execution.json")
        save(journal, record)
        tick = time.monotonic()
        with (audit / (name + ".stdout.log")).open("w") as stdout, (
            audit / (name + ".stderr.log")
        ).open("w") as stderr:
            process = subprocess.Popen(
                [
                    "/usr/bin/time",
                    "-v",
                    "-o",
                    str(audit / (name + ".resources.txt")),
                    *step["argv"],
                ],
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            record["pid"] = process.pid
            save(journal, record)
            peak_rss = peak_gpu = 0
            while process.poll() is None:
                rss, gpu = resources(process.pid)
                peak_rss, peak_gpu = max(peak_rss, rss), max(peak_gpu, gpu)
                time.sleep(3)
            code = process.returncode
        missing = [
            path for path in step["expected_products"] if not (output / path).is_file()
        ]
        record.update(
            status="completed" if code == 0 and not missing else "failed",
            returncode=code,
            ended_utc=utc(),
            elapsed_seconds=time.monotonic() - tick,
            peak_sampled_aggregate_rss_kib=peak_rss,
            peak_sampled_own_gpu_mib=peak_gpu,
            missing_products=missing,
            stdout_sha256=digest(audit / (name + ".stdout.log")),
            stderr_sha256=digest(audit / (name + ".stderr.log")),
        )
        save(journal, record)
        state["steps"].append(record)
        state["raw_unchanged"] = digest(source) == row["raw_sha256"]
        if record["status"] != "completed" or not state["raw_unchanged"]:
            state.update(stage="failed", failed_step=name, ended_utc=utc())
            save(audit / "pilot_status.json", state)
            return 1
        if args.through == "preprocess1":
            state.update(stage="preprocess1_completed", ended_utc=utc())
            save(audit / "pilot_status.json", state)
            return 0
    state.update(
        stage="computed_pending_independent_output_and_scale_review", ended_utc=utc()
    )
    save(audit / "pilot_status.json", state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
