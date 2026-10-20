# PrimateX Agent Backend: Detailed Technical Report

## Abstract

This report documents the current PrimateX Agent backend implementation under `modules/agent`. The backend is a FastAPI service that exposes an OpenAI-compatible tool-calling interface to PrimateX workflows, filesystem inspection utilities, official sample-data onboarding, and task management. The current version is no longer a single DeepSeek-only, two-call prototype: it supports platform-managed and caller-supplied LLM providers, a bounded multi-round agent loop, server-enforced workspace isolation, and a broader skill catalog.

## 1. System Overview and Architecture

The Agent backend is organized as a small FastAPI application with implementation split across focused backend modules.

**Entrypoint**

- `modules/agent/app.py`

**Backend modules**

- Configuration/constants: `modules/agent/backend/config.py`
- Pydantic/dataclass models: `modules/agent/backend/models.py`
- Skill and knowledge loading: `modules/agent/backend/skills.py`
- Task registry and executor lifecycle: `modules/agent/backend/tasks.py`
- Pipeline command construction and execution: `modules/agent/backend/pipeline.py`
- OpenAI-compatible LLM client: `modules/agent/backend/llm.py`
- Tool validation and execution: `modules/agent/backend/tools.py`
- FastAPI route wiring: `modules/agent/backend/api.py`

The server currently exposes these Agent routes:

- `GET /api/agent/skills`: list loaded skills and JSON schemas.
- `GET /api/agent/models`: list platform-managed model choices without exposing the platform API key.
- `GET /api/agent/tasks`: list in-memory Agent-submitted pipeline tasks.
- `POST /api/agent/chat`: run the LLM-assisted tool-calling loop.

All routes pass through the optional bearer-token guard controlled by `PRIMX_ACCESS_TOKEN`. If this environment variable is unset, token enforcement is disabled.

Code references:

- App construction and routes: `modules/agent/backend/api.py`
- Entrypoint: `modules/agent/app.py`
- Startup helper and dynamic port writing: `modules/agent/start-agent-backend.sh`

## 2. Provider and Model Handling

The chat endpoint supports two provider modes through `AgentChatRequest.provider`.

### 2.1 Platform Provider

`provider: "platform"` uses a server-side API key from `PLATFORM_API_KEY`, a base URL from `PLATFORM_API_BASE_URL`, and a model selected from `modules/agent/platform_models.json`. The default platform base URL is `https://api.modelverse.cn/v1`.

This mode is intended for deployment where the browser should not receive an API key. The `/api/agent/models` endpoint returns only model IDs and labels plus `platformAvailable`; it never returns the key.

Code references:

- Platform config: `modules/agent/backend/config.py`
- Model listing and validation: `modules/agent/backend/api.py`
- Model catalog: `modules/agent/platform_models.json`

### 2.2 Custom Provider

`provider: "custom"` requires the caller to provide `apiKey` and `model`, with optional `baseUrl`. If `baseUrl` is omitted, the backend uses `https://api.openai.com/v1`. Because the LLM client posts to `<baseUrl>/chat/completions`, this mode can target OpenAI-compatible APIs such as OpenAI, DeepSeek-compatible deployments, or other compatible gateways.

Code references:

- Request model aliases: `modules/agent/backend/models.py`
- Provider validation: `modules/agent/backend/api.py`
- LLM request implementation: `modules/agent/backend/llm.py`

## 3. Tool-Aware LLM Loop

The backend exposes skills as OpenAI-compatible function tools. The LLM request payload includes:

- `model`
- `messages`
- `tools`
- `tool_choice: "auto"`

The backend now runs a bounded multi-round tool loop rather than a fixed two-call flow. For each iteration up to `MAX_AGENT_ITERS`:

1. Call the selected OpenAI-compatible `/chat/completions` endpoint.
2. If the model returns no tool calls, use the model text as the final response.
3. If tool calls are returned, append the assistant tool-call message, execute each tool locally, append JSON `role: "tool"` results, and continue.
4. Two iterations before the hard limit, append a wrap-up instruction asking the model to stop calling tools and summarize.
5. If the hard limit is reached, return a fallback message and set `metadata.hitIterationLimit`.

`MAX_AGENT_ITERS` is read from `AGENT_MAX_ITERS` and clamped to at least 1.

Code references:

- Multi-round loop and fallback handling: `modules/agent/backend/api.py`
- Iteration config: `modules/agent/backend/config.py`
- Tool result serialization: `modules/agent/backend/api.py`
- LLM client: `modules/agent/backend/llm.py`

## 4. Skill Registry and Prompt Context

Skills are discovered from `modules/agent/skills/<skill-name>/`. A skill is loaded only when:

- `SKILL.md` exists.
- YAML frontmatter contains `name` and `description`.
- The frontmatter `name` exactly matches the folder name.
- `assets/parameters.json` exists and is valid JSON.

Each loaded skill is converted into:

```json
{
  "type": "function",
  "function": {
    "name": "...",
    "description": "...",
    "parameters": {}
  }
}
```

The system message includes operational instructions, server-side workspace rules, official sample-data rules, project knowledge from `modules/agent/knowledge.md`, and optional caller context. If `context.maxConcurrentTasks` is present, the backend resizes the thread pool. If `context.workspaceDirectory` is present, it becomes the enforced workspace for tool execution.

Code references:

- Skill parsing and schema construction: `modules/agent/backend/skills.py`
- Knowledge cache: `modules/agent/backend/skills.py`
- System message and context injection: `modules/agent/backend/api.py`

### 4.1 Progressive Skill Disclosure

Skill instructions use progressive disclosure and a two-phase runtime. The initial LLM request exposes a compact Skill catalog and a read-only `load-skill` selector; action tools are not available yet. When the model loads a Skill, the backend adds the complete `SKILL.md` to the trusted system message and exposes that Skill's action tool on the next LLM request. The action itself is called only once, after planning with the loaded instructions.

The runtime enforces a strict phase barrier: if any new Skill is loaded in a model response, no action tool from that response executes, including already-loaded actions mixed into the same response. The model must re-plan and issue actions in a later response. Pure loading rounds do not consume `MAX_AGENT_ITERS`; a separate hard bound of `MAX_AGENT_ITERS + number_of_loaded_skills` caps total LLM calls.

## 5. Workspace Isolation and Path Safety

Recent Agent changes added a stronger workspace boundary. The backend does not trust the LLM-provided `workspaceDirectory` when `context.workspaceDirectory` is present. Instead, `execute_tool(..., enforced_workspace=...)` overwrites tool arguments with the server-provided workspace root.

Filesystem tools use `_safe_resolve()` to:

- Resolve the workspace root and requested subpath.
- Reject shallow workspace roots with fewer than three path components.
- Reject path traversal outside the workspace root.

This protection applies to subject listing, subject tree rendering, log tailing, workspace listing, T1 discovery, sample discovery, and sample copying. Official sample data are not used directly as pipeline inputs; `use-sample-data` copies the chosen sample into the caller's own namespace first.

Code references:

- Workspace override in tool execution: `modules/agent/backend/tools.py`
- `_safe_resolve()` path validation: `modules/agent/backend/tools.py`
- Sample-data flow: `modules/agent/backend/tools.py`
- Workspace instructions in system prompt: `modules/agent/backend/api.py`

## 6. Pipeline Execution and Task Management

Pipeline execution is asynchronous and in-memory.

### 6.1 Task Store and Executor

`TaskStore` stores `PipelineTask` objects in memory. The general thread pool executor is created lazily and can be resized by `context.maxConcurrentTasks`, clamped to the range 1-64. All pipelines use this executor. Inside each runner, `seg-brain` and `seg-wm` acquire a shared resource lock immediately before their subprocess starts and release it as soon as that step exits, so only deep-learning segmentation is serialized while other steps retain configured parallelism. Running subprocesses are tracked in `PROCESS_REGISTRY` for cancellation and shutdown cleanup.

Code references:

- Task store and executor: `modules/agent/backend/tasks.py`
- `maxConcurrentTasks` handling: `modules/agent/backend/api.py`

### 6.2 Pipeline Command Construction

`run-pipeline` and single-step skills map to `primx` CLI calls. Supported steps are:

- `preprocess-1`
- `seg-brain`
- `acpc-align`
- `seg-wm`
- `preprocess-3`
- `rescale`
- `freesurfer2caret`
- `fastsurfer`

Validation enforces step constraints:

- `fastsurfer` must run as a standalone step.
- `fastsurfer` accepts only `species=Human` when a species is provided.
- Preprocess, segmentation, and FastSurfer steps that need an image require `t1Path`.
- Neuro steps require `species`.
- Segmentation steps require `segSpecies`.

Segmentation input paths are inferred from previous steps when possible: `seg-brain` can consume `T1.nii.gz` after `preprocess-1`, and `seg-wm` can consume `brain.nii.gz` after `seg-brain` or `acpc-align`.

Code references:

- Step whitelist: `modules/agent/backend/config.py`
- Validation and single-step wrapping: `modules/agent/backend/tools.py`
- Command construction: `modules/agent/backend/pipeline.py`
- Segmentation input selection: `modules/agent/backend/pipeline.py`

### 6.3 Logging, Status, Cancellation

Each pipeline task writes a log to:

```text
<workspaceDirectory>/<subjectId>/logs/agent_pipeline_<taskId>.log
```

Task responses include `taskId`, `status`, `currentStep`, `message`, `progress`, `subjectId`, `workspaceDirectory`, `outPath`, `species`, `segSpecies`, `steps`, `startTime`, `endTime`, `error`, and `logPath`.

`cancel-pipeline` marks the task as cancelled and attempts to terminate the active subprocess. On service shutdown, registered live subprocesses are also terminated.

Code references:

- Task response schema: `modules/agent/backend/pipeline.py`
- Pipeline run loop and logging: `modules/agent/backend/pipeline.py`
- Cancellation and shutdown cleanup: `modules/agent/backend/tools.py`, `modules/agent/backend/tasks.py`

## 7. Current Tool Catalog

The current filesystem skill registry contains 19 tools.

### 7.1 Pipeline Tools

- `run-pipeline`: run an ordered multi-step workflow.
- `preprocess-1`: run `primx neuro preprocess-1`.
- `seg-brain`: run `primx seg brain`.
- `acpc-align`: run `primx neuro acpc-align`.
- `seg-wm`: run `primx seg wm`.
- `preprocess-3`: run `primx neuro preprocess-3`.
- `rescale`: run `primx neuro rescale`.
- `freesurfer2caret`: run `primx neuro freesurfer2caret`.
- `fastsurfer`: run `primx human fastsurfer` for human T1 reconstruction.

### 7.2 Task and Inspection Tools

- `pipeline-status`: read in-memory task status.
- `cancel-pipeline`: cancel a running Agent task.
- `tail-log`: tail a log file under a subject directory.
- `subject-ls`: run targeted `ls -la` on one subject subfolder.
- `subject-tree`: render a recursive directory tree with file sizes.
- `workspace-ls`: list subject directories in a workspace, defaulting to `AGENT_DEFAULT_WORKSPACE`.
- `find-t1`: discover raw `.nii` / `.nii.gz` candidates at depth 1-2 while excluding known pipeline outputs.

### 7.3 Router and Sample-Data Tools

- `species-router`: run `primx seg router` to classify species and scalp/brain image type.
- `list-samples`: list official sample subjects in the fixed default workspace while excluding user namespace directories.
- `use-sample-data`: copy a chosen official sample into the caller's own input namespace and return the copied `t1Path`.

Code references:

- Skill definitions: `modules/agent/skills/*/SKILL.md`
- Tool schemas: `modules/agent/skills/*/assets/parameters.json`
- Tool dispatch: `modules/agent/backend/tools.py`

## 8. Recent Agent PR and Commit History

The current implementation reflects several recent Agent-focused changes:

- PR #15, `feat(agent): add subject-tree tool for single-call directory overview`, merged on 2026-05-25. It added `subject-tree`, updated `subject-ls` guidance, and replaced repeated listing chains with a Python recursive tree renderer.
- `daa99fc`: replaced the earlier single-round tool call with the bounded multi-round agent loop.
- `479ad29`: clamped `MAX_AGENT_ITERS` to at least 1 and surfaced `metadata.hitIterationLimit`.
- `213f171`: added default workspace onboarding via `workspace-ls` and `find-t1`.
- `c19380d`: hardened path handling with traversal protection and subject-tree safeguards.
- `1e8beba`: enforced per-user workspace isolation and added official sample-data tools.
- `6031675`: added platform-managed model selection alongside custom API-key mode.

Code references:

- PR #15 changed files: `modules/agent/backend/models.py`, `modules/agent/backend/tools.py`, `modules/agent/knowledge.md`, `modules/agent/skills/subject-ls/SKILL.md`, `modules/agent/skills/subject-tree/SKILL.md`, `modules/agent/skills/subject-tree/assets/parameters.json`
- Local history: `git log -- modules/agent docs/agent_backend_report.md`

## 9. Limitations and Open Issues

- **In-memory task state**: tasks are lost when the backend restarts.
  - Code reference: `modules/agent/backend/tasks.py`
- **No streaming log endpoint**: logs can be tailed through `tail-log`, but there is no server-sent events or websocket log stream.
  - Code reference: `modules/agent/backend/pipeline.py`
- **No persistent conversation store**: `conversationId` is returned, but history persistence is delegated to the caller; the backend relies on the `history` field passed into each request.
  - Code reference: `modules/agent/backend/api.py`
- **Skill loading is filesystem-only**: changes to skill markdown or JSON schemas are picked up by reload/re-read, but there is no admin API for skill validation or hot management.
  - Code reference: `modules/agent/backend/skills.py`
- **Task listing is global in-memory state**: `/api/agent/tasks` returns all Agent-submitted tasks currently stored in the process. Access control depends on the outer token/workspace deployment model.
  - Code reference: `modules/agent/backend/api.py`

## 10. Summary

The current PrimateX Agent backend is a modular FastAPI service that connects OpenAI-compatible chat-completion models to deterministic PrimateX tools. Compared with the earlier implementation, the current version adds platform-managed model selection, a bounded multi-round tool loop, stronger workspace isolation, safer filesystem tools, default workspace onboarding, official sample-data copying, subject tree inspection, task listing, and human FastSurfer support. The main remaining engineering gaps are persistence, streaming logs, and finer-grained task authorization.

---

**Document path:** `docs/agent_backend_report.md`
