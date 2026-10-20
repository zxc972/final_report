# PrimateX analysis coding agent — first implementation

This module adds an analysis mode to the existing PrimateX agent. The preprocessing
mode continues to use the existing CLI/pipeline tools. Analysis uses LangChain tools,
a Deep Agents coding loop, and an outer LangGraph with persistent SQLite state.

## Execution flow

```text
authenticated request -> inspect data + retrieve knowledge + write/run Python
                     -> validate current artifacts
                     -> repair (bounded) or report
```

The coding tools are `search_knowledge`, `read_knowledge`, `list_data`,
`read_data`, `write_code`, and `run_python`. Both agent modes additionally expose
`list_roots`, `ls`, `glob`, `grep`, `read_file`, `discover_subjects`,
`submit_pipeline`, and `pipeline_status`. Navigation accepts absolute registered
server paths; Python uses the corresponding `/inputs/N` mapping. The Deep Agents
virtual filesystem middleware is replaced to avoid duplicate tools reading an
unrelated virtual directory. Shell and delegation tools remain disabled.
The model writes Python based on
the requested task; it is not limited to a fixed analysis script catalog.

The outer graph has `coding`, `validate`, `repair`, and `report` nodes. A successful
report requires a successful Python execution in the current iteration and a fresh
`analysis_manifest.json` whose files pass validation. Prior manifests are archived
before execution. Each new request gets a separate `run_id` and output directory.

## Environments and startup

The service environment is `.venv-coding` (Python 3.11). Direct dependencies are in
`requirements-coding.txt`; the tested complete freeze is `requirements-coding.lock`.
The scientific runtime remains separate: Python from
`/data/xuancheng/structural_env/runtime/python-analysis` runs inside
`/data/xuancheng/agent/PrimateX_1_7.sif`, using Apptainer.

```bash
cd /data/xuancheng/agent/modules/agent
# On a fresh installation, create .venv-coding with Python 3.11 first.
.venv-coding/bin/python -m pip install -r requirements-coding.lock
./start-coding-backend.sh
```

The startup script defaults to `127.0.0.1:8110`. It does not replace another
PrimateX service. `AGENT_HOST`, `AGENT_PORT`, and `AGENT_CODING_PYTHON` override
these defaults. The Node backend and this agent must use the same
`PRIMX_ACCESS_TOKEN` for their user-session signatures to agree. Configure secrets
through the existing deployment environment; never put them in source or knowledge.
Platform models use the existing `PLATFORM_API_KEY` and platform model catalog.
Custom model settings are supplied by the existing frontend configuration.

`PRIMATEX_PIPELINE_IMAGE` enables CLI jobs inside the configured PrimateX SIF.
The startup script selects `/data/xuancheng/agent/PrimateX_1_7.sif`. Pipeline jobs
bind source data read-only and the output workspace read-write, and segmentation
steps use `--nv`. `PRIMATEX_FREESURFER_LICENSE` optionally supplies a host license
file to the container. An empty image setting when launching the Python service
directly retains the legacy host CLI execution path.

`GET /api/agent/analysis/health` checks dependency versions, not model connectivity
or sandbox readiness. The sandbox runs a real isolation probe before every code
execution and refuses execution when it fails.

## API and outputs

`POST /api/agent/chat` accepts `mode: "pipeline"` (default) or `mode: "analysis"`.
`POST /api/agent/analysis` is the explicit analysis endpoint. Both analysis routes
require the existing user ID, authenticated user token, and an absolute
`<workspaceRoot>/<userId>/output` workspace. Do not send an API key as prompt text.

```json
{
  "mode": "analysis",
  "provider": "platform",
  "model": "<configured-model-id>",
  "message": "Inspect the subject table, check missing values, and summarize thickness by group with units and limitations.",
  "context": {
    "userId": "<authenticated-user-id>",
    "userToken": "<session-token>",
    "workspaceDirectory": "/path/to/workspace/<authenticated-user-id>/output"
  }
}
```

Responses include `conversationId` and metadata with `status`, `run_id`,
`output_directory`, declared artifacts, validation results, and execution counts.
The output directory is relative to the approved workspace; artifact paths are
relative to that output directory. Code, tables, figures, summaries and manifests
remain there. Checkpoints and a durable budget ledger are stored outside the
sandbox in `.analysis_state` (override with `AGENT_ANALYSIS_STATE_DIR`). API keys
and user tokens are not placed in graph state.

For API-level recovery, resend the same `conversationId` with `resume: true`, the
same user/workspace/approved inputs and model configuration. A completed run is
returned without executing it again. An interrupted graph resumes from its saved
node; an external process interrupted mid-node is not an exactly-once transaction.
The original deadline and reserved call counts persist across recovery.

The frontend includes a Preprocessing / Coding analysis selector. Browser refresh
recovery and an analysis-job history screen are not implemented yet. New requests
preserve recent conversation text; they do not automatically mount previous runs'
files. Reusing old outputs requires an operator-approved read-only input grant.

## Data and execution boundaries

Allowed input roots are the user's `input` directory, visible subject directories
under their `output`, and operator grants in `AGENT_DATA_ROOTS` (colon separated
on Linux; fallback to `AGENT_ANALYSIS_DATA_ROOTS`). These grants apply to both modes.
The startup script registers `/data/xuancheng/datasets`, `human`, `human_fastsurfer`,
`T1WI_101`, `t1_neurodiscovery`, and `featurize_20261011` under `/data/xuancheng`.
Optional request `inputRoots` can narrow these grants. Additional data locations
are registered by changing `AGENT_DATA_ROOTS`, without relocating source files.
The startup script also sets `AGENT_DATA_DIRECTORY=/data/xuancheng`: each request
discovers its current data subdirectories, so a newly added cohort folder becomes
available automatically. `agent`, `structural_env`, hidden directories and user
authentication namespaces are excluded; names can be set with
`AGENT_DATA_EXCLUDE_DIRS`. `ls /data/xuancheng` shows the registered data folders.
`list_roots` reports actual server paths and mapped Python paths.
Paths containing symlinks and hidden/private files are rejected.

`discover_subjects` supports BIDS subject/session, subject/T1 folders and flat
NIfTI files, and reports multiple candidate scans explicitly. It does not infer
species. `submit_pipeline` uses the selected T1 in place and writes into the
authenticated output workspace. Existing nonempty subject outputs are preserved.
Submission receipts in the protected state directory deduplicate identical
requests across repeated calls/recovery. Changed parameters require another
output subject ID. Task workers still live in process memory: after a backend
restart a retained receipt is `unknown_after_restart`, and existing logs must be
inspected before a new run. A submitted task is never reported as completed
reconstruction. Inspection-only requests finish without fabricated artifacts.

Python sees inputs as `/inputs/0`, `/inputs/1`, etc. (read-only), and its own
`/work` (writable). Apptainer uses a read-only image, clean environment, isolated
network namespace, no host home or GPU, and no host shell fallback. The execution
probe checks the actual network, input write protection, hidden host paths,
runtime imports and enforced resource limits. Code execution is serialized.

Bounds: 3 coding/validation rounds, 18 model calls, 40 tool calls, 6 executions,
900 seconds per run, and at most 120 seconds per Python execution. The default
hard limits are 8 GiB of address space per process and 1 GiB per output file.
Operators can set integer-byte `AGENT_ANALYSIS_MEMORY_BYTES` and
`AGENT_ANALYSIS_FILE_BYTES`. These are not aggregate memory, process-count or total
disk quotas; those require administrator-provided cgroups/filesystem quotas.

## Knowledge and scientific scope

`knowledge_analysis/` contains the versioned research catalog (56 entries), runtime
inventory and three draft capabilities. `KnowledgeStore` currently performs bounded
lexical search and strict ID reads. It is a working retrieval baseline; it is not a
complete indexed software tutorial corpus or a biological knowledge graph.
Source tutorials are evidence, not executable instructions. Source links, runtime
versions, review state and applicability belong with each capability.

`analysis_validation.py` checks CSV/TSV, JSON and PNG outputs, paths, non-finite
values, identity constraints and declared shapes. Optional server-owned reference
manifests support independent numerical comparison. They are exercised in tests
but are not globally configured for arbitrary API requests. The default result
therefore reports `scientific_status: not_evaluated` and
`independent_numeric_status: not_configured`. Passing these checks does not prove
anatomical validity, appropriate statistics, or that an interpretation follows
from the cited literature.

The next knowledge work is to turn installed software's official usage examples
into reviewed capabilities and task-specific reference evaluations, starting with
FreeSurfer regional measures, Workbench surface/parcellation operations and
subject-table statistical analyses. Biological priors remain a separate evidence
layer with species, atlas, space, units, provenance and uncertainty.

## Verification

From `/data/xuancheng/agent`:

```bash
PRIMATEX_SANDBOX_INTEGRATION=1 PRIMATEX_RUN_SANDBOX_TESTS=1 \
  modules/agent/.venv-coding/bin/python -m pytest modules/agent/tests -q
```

The end-to-end test uses a deterministic scripted model with the real Deep Agents,
LangGraph, Apptainer and artifact validator. It computes a synthetic CSV summary,
compares it against an independent Decimal reference outside the sandbox, then
checks that a deliberately altered result is rejected. This verifies orchestration
and execution, not live-model reasoning or performance on PRIME_DE. No real-data
scientific result is asserted by this implementation test.
