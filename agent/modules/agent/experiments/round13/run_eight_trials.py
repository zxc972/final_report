"""At most eight round-13 cases with classified model and environment stops."""

from pathlib import Path
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path("/data/xuancheng/agent_round13_trial_20261022")
configuration = json.loads((ROOT / "operator_config.json").read_text())
USER = configuration["user_id"]
WORKSPACE = Path(configuration["workspace"])
salt = json.loads((WORKSPACE.parent / ".auth.json").read_text())["salt"]
signing = hmac.new(b"", salt.encode(), hashlib.sha256).hexdigest().encode()
encoded = (
    base64.urlsafe_b64encode(f"{USER}:{int(time.time()) + 86400}".encode())
    .decode()
    .rstrip("=")
)
user_token = (
    encoded + "." + hmac.new(signing, encoded.encode(), hashlib.sha256).hexdigest()
)
questions = [('R13_P1_1', 'Summarise cortical thickness for each region of the aparc parcellation in both hemispheres of the macaque reconstruction in the registered data. Keep the native stored scale, restrict to cortex, and report units and limitations.'), ('R13_P1_2', 'Summarise cortical thickness for each region of the aparc parcellation in both hemispheres of the macaque reconstruction in the registered data. Keep the native stored scale, restrict to cortex, and report units and limitations.'), ('R13_P2_1', 'For the macaque reconstruction in the registered data, compute a true local gyrification index if its prerequisites are met. If they are not met, explain what is missing and complete any feasible related descriptive analysis instead.'), ('R13_P3_1', 'Which subjects and reconstruction outputs are available in my registered data? Do not start any processing.'), ('R13_H1_1', '计算该被试左右半球各 DKT 分区的平均皮层厚度'), ('R13_H2_1', '比较该被试左右半球 DKT 分区皮层厚度的不对称')]
BASE = "http://127.0.0.1:8130"
with urllib.request.urlopen(BASE + "/api/agent/models", timeout=10) as response:
    assert response.status == 200
summary = []
consecutive_limited = 0
(ROOT / "audit/backend_ready.json").write_text(
    json.dumps(
        {
            "ready": True,
            "endpoint": "/api/agent/models",
            "model": configuration["model"],
            "time": time.time(),
        },
        indent=2,
    )
)
print(
    json.dumps(
        {
            "backend_ready": True,
            "model": configuration["model"],
            "cases": 8,
        }
    ),
    flush=True,
)

PRO = "deepseek-v4-pro"
FLASH = "deepseek-v4.1-flash"
questions += [('R13_FLASH_P1_1', 'Summarise cortical thickness for each region of the aparc parcellation in both hemispheres of the macaque reconstruction in the registered data. Keep the native stored scale, restrict to cortex, and report units and limitations.'), ('R13_FLASH_P1_2', 'Summarise cortical thickness for each region of the aparc parcellation in both hemispheres of the macaque reconstruction in the registered data. Keep the native stored scale, restrict to cortex, and report units and limitations.')]
import importlib.util
classification_spec = importlib.util.spec_from_file_location("r11_failure_policy", ROOT / "backend_review/backend/analysis_failure_classification.py")
classification = importlib.util.module_from_spec(classification_spec)
classification_spec.loader.exec_module(classification)
classify, should_stop = classification.classify, classification.should_stop
model_stops = {}
p1_results = {}
for case, question in questions:
    selected_model = FLASH if case.startswith("R13_FLASH") else PRO
    if selected_model in model_stops:
        continue
    if '_H2_' in case and not json.loads((ROOT/'stage0/offline_ready.json').read_text()).get('H2_ready'):
        continue
    if (ROOT / "audit/environment_auth_pause.json").exists():
        print("ENVIRONMENT_AUTH_PAUSE: no subsequent case dispatched", flush=True)
        break
    if (ROOT / "audit/safety_stop.json").exists():
        print("SAFETY_STOP: remaining cases were not dispatched", flush=True)
        break
    assert not (
        ROOT / "trials" / case
    ).exists(), "Never repeat an already-dispatched case"
    conversation = case.lower() + "_" + uuid.uuid4().hex[:12]
    payload = {
        "message": question,
        "mode": "auto",
        "provider": "platform",
        "model": selected_model,
        "conversationId": conversation,
        "inputRoots": [configuration["input_roots"][1]] if "_H1_" in case or "_H2_" in case else configuration["input_roots"],
        "context": {
            "userId": USER,
            "workspaceDirectory": str(WORKSPACE),
            "userToken": user_token,
        },
    }
    started = time.monotonic()
    print(
        json.dumps(
            {"case": case, "conversation_id": conversation, "status": "started"}
        ),
        flush=True,
    )
    request = urllib.request.Request(
        BASE + "/api/agent/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Trial-Case": case},
    )
    folder = ROOT / "trials" / case
    try:
        with urllib.request.urlopen(request, timeout=1210) as response:
            result = json.load(response)
        status = 200
    except urllib.error.HTTPError as error:
        status = error.code
        text = error.read().decode("utf-8", "replace")
        try:
            result = json.loads(text)
        except ValueError:
            result = {"error_type": "NonJSONHTTPError"}
    except Exception as error:
        status = None
        result = {"error_type": type(error).__name__}
        if time.monotonic() - started >= 1200:
            (ROOT / "audit/safety_stop.json").write_text(
                json.dumps(
                    {
                        "reason": "Client observed wall-clock budget exceeded",
                        "case": case,
                        "time": time.time(),
                    }
                )
            )
    assert user_token not in json.dumps(result), "Never persist session tokens"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "agent_response.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    events = []
    last = 0
    view = {}
    for page in range(10):
        query = urllib.parse.urlencode(
            {"userId": USER, "workspaceDirectory": str(WORKSPACE), "after": last}
        )
        try:
            with urllib.request.urlopen(
                BASE + f"/api/agent/analysis/{conversation}/events?" + query, timeout=10
            ) as response:
                view = json.load(response)
        except Exception as error:
            view = {"error_type": type(error).__name__}
            break
        batch = view.get("events", [])
        events.extend(batch)
        if not view.get("has_more") or not batch:
            break
        last = max(item["seq"] for item in batch)
    event_view = {**view, "events": events, "has_more": False}
    (folder / "events_response.json").write_text(
        json.dumps(event_view, ensure_ascii=False, indent=2)
    )
    with (folder / "events.jsonl").open("w") as stream:
        for event in events:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    metadata = result.get("metadata", {})
    row = {
        "case": case,
        "model": selected_model,
        "conversation_id": conversation,
        "http_status": status,
        "route": metadata.get("route"),
        "status": metadata.get("status"),
        "model_calls": metadata.get("model_calls"),
        "executions": metadata.get("executions"),
        "iterations": metadata.get("iterations"),
        "event_count": len(events),
        "elapsed_seconds": time.monotonic() - started,
    }
    summary.append(row)
    (ROOT / "trial_progress.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(row), flush=True)
    if "P1" in case:
        from private_review import review

        checked = review(case)
        row["independent_p1_passed"] = checked["passed"]
        row["product_numeric_status"] = metadata.get("validation", {}).get("independent_numeric_status")
        row["product_numeric_mismatches"] = metadata.get("validation", {}).get("independent_numeric", {}).get("mismatch_count")
        row["independent_parcels_checked"] = checked["checked_parcels"]
        (ROOT / "trial_progress.json").write_text(json.dumps(summary, indent=2))
        print(
            json.dumps(
                {
                    "case": case,
                    "independent_p1_passed": checked["passed"],
                    "parcels_checked": checked["checked_parcels"],
                }
            ),
            flush=True,
        )
    validation = metadata.get("validation", {})
    internal = validation.get("internal_review", {})
    public = validation.get("public_output_contract", {})
    row.update(
        public_contract_status=public.get("status"),
        internal_review_decision=internal.get("decision"),
        internal_review_protocol_valid=internal.get("protocol_valid"),
        phase_budget=metadata.get("phase_budget"),
        overall_status=metadata.get("overall_status"),
    )
    if "P1" in case:
        row["full_p1_passed"] = bool(
            metadata.get("status") == "completed"
            and public.get("status") == "pass"
            and validation.get("independent_numeric_status") == "pass"
            and internal.get("decision") == "pass"
            and internal.get("protocol_valid") is True
            and checked.get("passed")
            and checked.get("automatic_finalization")
            and checked.get("protected_receipts_verified")
        )
    elif "P2" in case:
        from private_review import review
        hull_checked = review(case)
        row["independent_hull_passed"] = hull_checked.get("numerical_passed", False)
        row["product_numeric_status"] = validation.get("independent_numeric_status")
    if "_H1_" in case or "_H2_" in case:
        from human_cached_review import review_human
        row["external_human_review"] = review_human(case)
    row["task_kind"] = metadata.get("task_kind")
    row["inspection_validation_passed"] = validation.get("passed") if "P3" in case else None
    row["failure_classification"] = classify(metadata, None if "P3" in case else "analysis")
    failures = [item["failure_classification"] for item in summary
                if item["model"] == selected_model and "failure_classification" in item]
    if should_stop(failures):
        model_stops[selected_model] = {
            "reason": "Two failures with the same specific root cause",
            "failures": failures, "cases": [item["case"] for item in summary if item["model"] == selected_model],
        }
        (ROOT / "audit/model_stops.json").write_text(json.dumps(model_stops, indent=2))
    model_p1 = [item for item in summary if item["model"] == selected_model and "P1" in item["case"]]
    if "P1" in case and len(model_p1) == 2:
        gate = {
            "allowed": any(item.get("full_p1_passed") for item in model_p1) and selected_model not in model_stops,
            "model": selected_model,
            "fully_passed_cases": [item["case"] for item in model_p1 if item.get("full_p1_passed")],
            "time": time.time(),
        }
        (ROOT / "audit/p1_continuation_gate.json").write_text(json.dumps(gate, indent=2))
    (ROOT / "trial_progress.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"case": case, "full_p1_passed": row.get("full_p1_passed"), "root_cause": row["failure_classification"]}), flush=True)
    action = classification.rate_limit_batch_action(consecutive_limited, row["failure_classification"])
    consecutive_limited = action["consecutive_rate_limited"]
    if action["stop_batch"]:
        (ROOT / "audit/environment_batch_stop.json").write_text(json.dumps({**action, "case": case, "reason": action.get("reason", "Two consecutive environment-rate-limited cases"), "time": time.time()}, indent=2))
        print("ENVIRONMENT_STOP: " + action.get("reason", "two consecutive rate-limited cases"), flush=True)
        break
    if action["pause_seconds"] and case != questions[-1][0]:
        pause = {**action, "after_case": case, "started_time": time.time()}
        (ROOT / "audit/environment_pause.json").write_text(json.dumps(pause, indent=2))
        started_pause = time.monotonic()
        time.sleep(action["pause_seconds"])
        pause.update(actual_seconds=time.monotonic()-started_pause, finished_time=time.time())
        (ROOT / "audit/environment_pause.json").write_text(json.dumps(pause, indent=2))

    if (ROOT / "audit/safety_stop.json").exists():
        print("SAFETY_STOP: no subsequent case dispatched", flush=True)
        break
print("ROUND13_DISPATCH_FINISHED", flush=True)
