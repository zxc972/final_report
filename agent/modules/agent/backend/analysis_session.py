"""Host-owned analysis phases and mechanical, receipt-backed finalization."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json

from .analysis_control_store import digest

SESSION_PROFILES = {"product_graph_planner"}


class AnalysisSession:
    def __init__(self, tools):
        self.tools = tools
        saved = tools.control_store.latest("session")
        self.record = (
            copy.deepcopy(saved["record"])
            if saved
            else {
                "phase": "unplanned",
                "plan_version": None,
                "code_path": None,
                "exit_code": None,
                "outputs_complete": False,
                "missing": [],
                "automatic_finalizations": 0,
                "wrong_path_blocks": 0,
            }
        )
        # Model-call counters are independent of phase-transition records.
        saved_budget = tools.control_store.latest("phase_budget")
        if saved_budget:
            self.record.update(saved_budget["record"])
        saved_control = tools.control_store.latest("planning_control")
        if saved_control:
            self.record.update(saved_control["record"])
        if saved is None:
            self._save("unplanned", "Choose a feasible plan_analysis candidate")

    def _save(self, phase, next_step, **fields):
        previous = self.record.get("phase")
        self.record.update(fields, phase=phase, next=next_step)
        self.tools.control_store.save("session", self.record)
        if previous != phase and self.tools.events is not None:
            status = "failed" if phase == "executed_failed" else "done"
            self.tools.events.append(
                "review" if phase.startswith("executed") else "plan",
                status,
                "Analysis phase: " + phase,
                {
                    "phase": phase,
                    "previous_phase": previous,
                    "plan_version": self.record.get("plan_version"),
                },
            )

    def refresh(self):
        plan = self.tools.control_store.latest("plan")
        if plan and plan["version"] != self.record.get("plan_version"):
            self._save(
                "sealed",
                "Write and run the sealed script",
                plan_version=plan["version"],
                code_path=plan["record"]["plan"]["code_path"],
                outputs_complete=False,
                missing=[],
                finalized_receipt=None,
                written_plan_version=None,
            )
        elif plan is None and self.record["phase"] == "unplanned":
            planning = self.tools.control_store.latest("planning_result")
            if planning and planning["record"].get("candidates"):
                self._save("planned", "Select a candidate and call commit_plan")

    def state(self):
        self.refresh()
        value = {
            key: self.record.get(key)
            for key in ("phase", "code_path", "exit_code", "outputs_complete", "next")
        }
        if self.record.get("missing"):
            value["missing"] = self.record["missing"][:2]
        while len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) > 400:
            if value.get("missing"):
                value["missing"] = [str(value["missing"][0])[:70]]
                if (
                    len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
                    <= 400
                ):
                    break
                value.pop("missing")
            else:
                value["next"] = "See protected session record; repair and rerun"
                break
        if len(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) > 400:
            value["code_path_ref"] = "sealed plan"
            value.pop("code_path")
        return value

    def guard_write(self, path):
        self.refresh()
        sealed = self.record.get("code_path")
        if sealed and path != sealed:
            self.record["wrong_path_blocks"] += 1
            self.tools.control_store.save("session", self.record)
            raise ValueError(
                f"Plan sealed with code_path={sealed}. Edit {sealed} instead, "
                "or call commit_plan again to re-seal with a new code_path."
            )

    def wrote_code(self, path):
        if path == self.record.get("code_path"):
            self._save(
                "sealed",
                f"Run {path}",
                written_plan_version=self.record["plan_version"],
                outputs_complete=False,
                finalized_receipt=None,
                missing=[],
            )

    def execution_path(self, path):
        self.refresh()
        if path is None:
            path = self.record.get("code_path")
            if not path:
                raise ValueError("Call commit_plan before omitting the script path")
        return path

    def review_failed(self, validation):
        """Reopen repair after actual graph validation, without discarding receipts."""
        self.refresh()
        if self.record["phase"] != "finalized":
            return
        from .analysis_agent import _write_regular
        from .analysis_independent_numeric import public_model_validation
        validation = public_model_validation(validation)

        path = "/work/tool_results/validation_feedback.json"
        target = self.tools.resolve(path, writable=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_regular(
            target, self.tools.workdir, json.dumps(validation, ensure_ascii=False)
        )
        self._save(
            "executed_failed",
            "Read /work/tool_results/validation_feedback.json; revise the sealed script and rerun",
            outputs_complete=False,
            finalized_receipt=None,
            review_pending=True,
            rejected_execution_receipt_id=self.tools.last_execution.get("receipt_id"),
            missing=[
                "Graph validation requested a revision; see validation_feedback.json"
            ],
        )

    def artifact_contract(self):
        saved = self.tools.control_store.latest("execution_bundle")
        if saved is None:
            raise ValueError("Sealed execution bundle is missing")
        plan = self.tools.control_store.latest("plan")
        if saved["record"]["plan_sha256"] != plan["sha256"]:
            raise ValueError("Execution bundle does not match sealed plan")
        contract = saved["record"]["output_contract"]
        specs, missing = [], []
        for declared in contract["files"]:
            spec = dict(declared) if isinstance(declared, dict) else {"path": declared}
            path = spec["path"].removeprefix("/work/")
            spec["path"] = path
            suffix = path.rsplit(".", 1)[-1].lower()
            kind = spec.setdefault(
                "kind", {"md": "markdown", "txt": "text"}.get(suffix, suffix)
            )
            target = self.tools.resolve("/work/" + path, writable=True)
            if not target.is_file():
                missing.append("Missing file: " + path)
                continue
            from .analysis_validation import MAX_ARTIFACT_BYTES
            from .analysis_agent import _read_regular

            raw = _read_regular(target, self.tools.workdir, MAX_ARTIFACT_BYTES)
            if kind in {"csv", "tsv"}:
                reader = csv.reader(
                    io.StringIO(raw.decode("utf-8-sig")),
                    delimiter="\t" if kind == "tsv" else ",",
                )
                columns = next(reader, [])
                required = contract.get("csv_columns", [])
                for column in required:
                    if column not in columns:
                        missing.append(f"{path}: missing column {column}")
                spec.setdefault("columns", columns)
            elif kind == "json":
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeError):
                    missing.append(path + ": invalid JSON")
                    continue
                keys = contract.get("json_required_keys", [])
                for key in keys:
                    if not isinstance(payload, dict) or key not in payload:
                        missing.append(f"{path}: missing JSON key {key}")
                spec.setdefault("required_keys", keys)
            specs.append(spec)
        present = {spec["path"] for spec in specs}
        for path in self.tools.required_artifacts:
            if path not in present:
                missing.append("Missing caller artifact: " + path)
        return specs, missing

    def after_execution(self):
        execution = self.tools.last_execution
        gate = execution.get("plan_gate", {})
        if gate.get("read_only") or gate.get("plan_version") is None:
            return None
        self.refresh()
        exit_code = execution.get("exit_code")
        if execution.get("status") != "success" or exit_code != 0:
            self._save(
                "executed_failed",
                f"Edit {self.record['code_path']} and run it again",
                exit_code=exit_code,
                outputs_complete=False,
                finalized_receipt=None,
                missing=[],
            )
            return None
        self._save(
            "executed_ok",
            "Check required files and columns",
            exit_code=0,
            outputs_complete=False,
            missing=[],
        )
        try:
            # Only a new successful execution may satisfy a prior review repair.
            if self.record.get("review_pending") and self.tools.last_execution.get(
                "receipt_id"
            ) == self.record.get("rejected_execution_receipt_id"):
                raise ValueError("Review repair requires a new successful execution")
            self.record["review_pending"] = False
            specs, missing = self.artifact_contract()
            if missing:
                raise ValueError("; ".join(missing))
            from .analysis_output_contract import check_outputs
            public = check_outputs(self.tools)
            execution["public_output_contract"] = public
            if public["status"] == "fail":
                raise ValueError("Public output contract failed: " + "; ".join(
                    error for item in public["files"] for error in item["errors"]))
            from .analysis_precision import check_precision
            precision = check_precision(self.tools, specs)
            self.tools.control_store.save("precision", {"warnings": precision})
            if precision:
                self.tools.events.append("review", "warn", "Numeric output appears rounded", {
                    "files": [row["file"] for row in precision],
                    "columns": sorted({column for row in precision for column in row["columns"]}),
                })
                raise ValueError("numeric output appears rounded: " + "; ".join(
                    row["file"] + " columns " + ",".join(row["columns"]) for row in precision
                ))
            result = self.tools._finalize_artifacts_impl(specs)
            if result.get("status") != "finalized":
                raise ValueError(
                    json.dumps(result.get("validation", {}), ensure_ascii=False)
                )
        except Exception as exc:
            reason = str(exc)
            self._save(
                "executed_failed",
                ("Read /work/tool_results/validation_feedback.json; edit the sealed script and rerun"
                 if execution.get("public_output_contract", {}).get("status") == "fail"
                 else f"Repair outputs from {self.record['code_path']} and rerun"),
                missing=[reason],
                outputs_complete=False,
                finalized_receipt=None,
            )
            execution["automatic_finalization"] = {
                "status": "artifact_contract_failed",
                "error": reason,
            }
            return execution["automatic_finalization"]
        self._save(
            "finalized",
            "Outputs complete; finalized automatically, write the reply",
            outputs_complete=True,
            missing=[],
            finalized_receipt=result,
            automatic_finalizations=self.record.get("automatic_finalizations", 0) + 1,
            manifest_sha256=result["manifest_sha256"],
        )
        execution["automatic_finalization"] = {
            "status": "finalized",
            "artifact_receipt_id": result["artifact_receipt_id"],
            "manifest_sha256": result["manifest_sha256"],
        }
        from .analysis_independent_numeric import verify
        verify(self.tools)
        return execution["automatic_finalization"]

    def existing_receipt(self):
        self.refresh()
        receipt = self.record.get("finalized_receipt")
        if self.record["phase"] != "finalized" or receipt is None:
            return None
        from .analysis_validation import ArtifactValidator, MANIFEST_NAME

        path = self.tools.workdir / MANIFEST_NAME
        from .analysis_agent import _read_regular

        actual = hashlib.sha256(
            _read_regular(path, self.tools.workdir, 65536)
        ).hexdigest()
        current = ArtifactValidator().validate(self.tools.workdir)
        if actual != receipt["manifest_sha256"] or digest(current) != digest(
            receipt["validation"]
        ):
            raise ValueError(
                "Finalized outputs changed; execute the sealed script again"
            )
        return {**copy.deepcopy(receipt), "already_finalized": True}
