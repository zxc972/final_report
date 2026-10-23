"""Zero-model macaque batch follow-up with explicit, recorded acceptance gates."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(path, body):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def release_allowed(acceptance, policy):
    if not acceptance or acceptance.get("scale_verified") is not True:
        return False
    if acceptance.get("status") == "pass":
        return policy.get("full_pass_release") is True
    return (
        acceptance.get("status") == "conditional_pass"
        and policy.get("conditional_release") == "allow_global_warnings"
        and acceptance.get("subject")
        in policy.get("conditional_allowed_prerequisites", [])
    )


def process_alive(pid):
    path = Path("/proc") / str(pid) / "stat"
    try:
        return path.read_text().rpartition(")")[2].split()[0] != "Z"
    except OSError:
        return False


def resources_available():
    memory = next(
        int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    probe = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
    )
    gpu_free = int(probe.stdout.splitlines()[0]) if probe.returncode == 0 else 0
    return memory >= 20 * 1024 * 1024 and gpu_free >= 8 * 1024


def verify_bundle(bundle):
    manifest = json.loads((bundle / "bundle_sha256.json").read_text())
    if any(digest(bundle / path) != sha for path, sha in manifest.items()):
        raise ValueError("Frozen runtime bundle changed; refusing automatic work")


def start_case(case, config, bundle):
    root = Path(config["dataset_root"])
    audit = Path(config["audit_root"]) / case["subject"]
    output = root / "derivatives/primatex_1.7_PRIME_DE" / case["subject"]
    if output.exists() or audit.exists():
        raise ValueError(
            "Existing subject output/audit found; do not launch duplicate "
            + case["subject"]
        )
    rows = json.loads(Path(case["manifest"]).read_text())
    selected = [row for row in rows if row["subject_id"] == case["subject"]]
    if (
        len(selected) != 1
        or selected[0]["held_out"] is not False
        or selected[0]["species"] != "Macaca mulatta"
    ):
        raise ValueError("Unapproved or non-rhesus subject in queue")
    verify_bundle(bundle)
    audit.mkdir()
    shutil.copyfile(bundle / "inside_environment.sh", audit / "inside_environment.sh")
    command = [
        config["python"],
        "-B",
        str(bundle / "run_prime_primatex_pilot.py"),
        "--manifest",
        case["manifest"],
        "--subject",
        case["subject"],
        "--repo",
        config["primatex_repo"],
        "--image",
        config["image"],
        "--config",
        config["container_config"],
        "--license-file",
        config["license_file"],
        "--output",
        str(output),
        "--audit",
        str(audit),
        "--model-receipt",
        config["model_receipt"],
    ]
    with (audit / "supervisor.stdout.log").open("wb") as out, (
        audit / "supervisor.stderr.log"
    ).open("wb") as err:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
    save(
        audit / "launch.json",
        {
            "pid": proc.pid,
            "argv": command,
            "started_utc": utc(),
            "provider_requests": 0,
            "prerequisite": case["prerequisite"],
            "gate_policy": json.loads(Path(config["gate_policy"]).read_text()),
        },
    )
    return proc.pid


def accept_case(case, config, bundle):
    audit = Path(case["pilot_audit"])
    output = Path(config["audit_root"]) / (case["subject"] + "_automatic_acceptance")
    existing = output / "acceptance.json"
    if existing.exists():
        return json.loads(existing.read_text())
    if output.exists():
        raise ValueError("Partial acceptance output retained; no blind repeat")
    verify_bundle(bundle)
    worker = bundle / "agent/modules/agent/backend/analysis_global_reference_worker.py"
    command = [
        config["python"],
        "-B",
        str(bundle / "tools/accept_macaque_globals.py"),
        "--subject",
        case["subject"],
        "--outer",
        str(
            Path(config["dataset_root"])
            / "derivatives/primatex_1.7_PRIME_DE"
            / case["subject"]
        ),
        "--manifest",
        case["manifest"],
        "--pilot-audit",
        str(audit),
        "--output",
        str(output),
        "--reference-worker",
        str(worker),
    ]
    with (
        Path(config["audit_root"]) / (case["subject"] + "_acceptance.stdout.log")
    ).open("w") as out, (
        Path(config["audit_root"]) / (case["subject"] + "_acceptance.stderr.log")
    ).open(
        "w"
    ) as err:
        run = subprocess.run(command, stdout=out, stderr=err, timeout=360)
    save(
        Path(config["audit_root"]) / (case["subject"] + "_acceptance_execution.json"),
        {
            "argv": command,
            "returncode": run.returncode,
            "ended_utc": utc(),
            "provider_requests": 0,
        },
    )
    if run.returncode:
        raise ValueError("Acceptance tool failed; original outputs and logs retained")
    return json.loads(existing.read_text())


def run(config, bundle):
    audit_root = Path(config["audit_root"])
    lock = audit_root / "followup.lock"
    if lock.exists():
        prior = json.loads(lock.read_text())
        if process_alive(prior["pid"]):
            raise ValueError("A follow-up coordinator is already active")
        lock.rename(lock.with_name("followup.lock.previous." + str(time.time_ns())))
    with lock.open("x") as stream:
        json.dump({"pid": os.getpid(), "started_utc": utc()}, stream)
    accepted = {"ION_32198": json.loads(Path(config["ion_acceptance"]).read_text())}
    statuses = {}
    pending = [dict(case) for case in config["pending_cases"]]
    active = [dict(config["existing_first_uc"])]
    for case in pending[:]:
        prior_audit = audit_root / case["subject"]
        if (prior_audit / "launch.json").exists():
            case["pilot_audit"] = str(prior_audit)
            active.append(case)
            pending.remove(case)
    spawned = {}
    started = time.monotonic()
    while time.monotonic() - started < 24 * 3600:
        verify_bundle(bundle)
        policy = json.loads(Path(config["gate_policy"]).read_text())
        for case in active[:]:
            path = Path(case["pilot_audit"]) / "pilot_status.json"
            if not path.exists():
                launch = Path(case["pilot_audit"]) / "launch.json"
                pid = json.loads(launch.read_text())["pid"] if launch.exists() else None
                if pid and process_alive(pid):
                    continue
                statuses[case["subject"]] = {
                    "stage": "failed_supervisor_before_state",
                    "raw_outputs_preserved": True,
                }
                active.remove(case)
                continue
            state = json.loads(path.read_text())
            statuses[case["subject"]] = {
                "stage": state["stage"],
                "steps_completed": len(state["steps"]),
                "pid_alive": process_alive(state["pid"]),
            }
            if state["stage"].startswith("computed_") and not process_alive(
                state["pid"]
            ):
                accepted[case["subject"]] = accept_case(case, config, bundle)
                active.remove(case)
            elif not process_alive(state["pid"]):
                statuses[case["subject"]]["terminal_without_acceptance"] = True
                active.remove(case)
        for case in pending[:]:
            prerequisite = accepted.get(case["prerequisite"])
            if (
                release_allowed(prerequisite, policy)
                and len(active) < config["max_active_subjects"]
                and resources_available()
            ):
                pid = start_case(case, config, bundle)
                case["pilot_audit"] = str(audit_root / case["subject"])
                spawned[pid] = case["subject"]
                active.append(case)
                pending.remove(case)
                statuses[case["subject"]] = {
                    "stage": "launched",
                    "pid": pid,
                    "prerequisite": case["prerequisite"],
                }
        holds = [
            {
                "subject": case["subject"],
                "prerequisite": case["prerequisite"],
                "prerequisite_status": accepted.get(case["prerequisite"], {}).get(
                    "status"
                ),
                "conditional_release": policy.get("conditional_release"),
            }
            for case in pending
        ]
        body = {
            "updated_utc": utc(),
            "pid": os.getpid(),
            "active": [case["subject"] for case in active],
            "statuses": statuses,
            "acceptances": {
                sid: {
                    "status": a["status"],
                    "scale_verified": a["scale_verified"],
                    "metrics": a["metrics"]["physical"],
                }
                for sid, a in accepted.items()
            },
            "holds": holds,
            "model_api_requests": 0,
            "automatic_retries": 0,
            "pending": len(pending),
        }
        eligible_pending = any(
            release_allowed(accepted.get(case["prerequisite"]), policy)
            for case in pending
        )
        body["stage"] = (
            "running"
            if active
            else (
                "finished"
                if not pending
                else (
                    "waiting_resources"
                    if eligible_pending
                    else "waiting_user_gate_or_failed_prerequisite"
                )
            )
        )
        save(audit_root / "followup_status.json", body)
        if not active and not eligible_pending:
            break
        for pid in list(spawned):
            try:
                waited, _ = os.waitpid(pid, os.WNOHANG)
                if waited:
                    spawned.pop(pid)
            except ChildProcessError:
                spawned.pop(pid, None)
        time.sleep(30)
    else:
        save(
            audit_root / "followup_deadline.json",
            {
                "time": utc(),
                "reason": "Finite24h follow-up deadline reached; no worker/service stopped",
                "provider_requests": 0,
            },
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    run(json.loads(args.config.read_text()), args.bundle)


if __name__ == "__main__":
    main()
