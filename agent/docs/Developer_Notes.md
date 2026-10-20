# Developer Notes (PrimateX)

This file serves as a quick reference for developers.

## Monorepo layout

- Root CLI: `workflows/primx_cli/primx`
- Modules:
  - Neuro pipeline: `modules/neuro_pipeline/`
  - Segmentation: `modules/primx_seg/`
- GUI frontend: `modules/gui/monkey-brain-frontend/`
- GUI backend: `modules/gui/monkey-brain-backend/`
- Agent backend: `modules/agent/`

## primx CLI (workflows/primx_cli/primx)

- `neuro`: `preprocess-1`, `preprocess-3`, `preprocess-3-1`, `preprocess-3-2`, `rescale`, `freesurfer2caret`, `acpc-align`, `label-resample`, `image-reorient`
- `seg`: `brain`, `wm` (defaults `-model_dir modules/primx_seg/models` if omitted), `router`
- `gui`: `install-deps`, `start`, `start-backend`, `start-stack`

## GUI entrypoints

- Frontend start: `primx gui start` (runs `start-notebook.sh`)
- Backend start: `primx gui start-backend` (Node server)
- Agent backend start: `primx gui start-agent-backend` (FastAPI server)
- Stack start: `primx gui start-stack` (backend in bg + frontend)

## GUI backend (pipeline)

- Path: `modules/gui/monkey-brain-backend/server.js`
- Default port: `8000` (`PIPELINE_PORT` overrides)
- Endpoints:
  - `POST /api/pipeline/run`
  - `GET /api/pipeline/:id/status`
  - `POST /api/pipeline/:id/cancel`
- Executes `primx` steps (whitelist):
  `preprocess-1`, `seg-brain`, `acpc-align`, `seg-wm`, `preprocess-3`, `rescale`, `freesurfer2caret`
- Output dir rule: `outPath = workspaceDirectory/subjectId`
- Logs: `<outPath>/logs/pipeline_<taskId>.log`

## Agent backend

- Path: `modules/agent/app.py`
- Default port: `8100` (`AGENT_PORT` overrides)
- Endpoints:
  - `POST /api/agent/chat`
  - `GET /api/agent/skills`
- Skills docs: `modules/agent/skills/<skill>/SKILL.md`
- Logs: `<outPath>/logs/agent_pipeline_<taskId>.log`

## GUI frontend (pipeline page)

- Default port: `5173` (forced in `modules/gui/monkey-brain-frontend/start-notebook.sh`)
- Page: `modules/gui/monkey-brain-frontend/src/pages/PipelinePage.tsx`
- Uses store: `modules/gui/monkey-brain-frontend/src/stores/pipelineStore.ts`
- Service: `modules/gui/monkey-brain-frontend/src/services/pipelineService.ts`
- Types: `modules/gui/monkey-brain-frontend/src/types/pipeline.ts`
- Pipeline uses `workspaceDirectory` + `subjectId`, not explicit `outPath`
- `segSpecies` required for primx seg (`rhesus`, `cynomolgus`, `chimpanzee`, `marmoset`, `human`)

## ACPC Alignment script rule

- `modules/neuro_pipeline/ACPC_Alignment.sh`:
  - If `-species` set, reference auto-set:
    - Macaque → `template/Macaque/NMT_brain_05.nii.gz`
    - Chimpanzee → `template/Chimpanzee/ChimpYerkes29_T1w_0.8mm_brain.nii.gz`
    - Marmoset → `template/Marmoset/RIKENMarmoset15_AverageT1w_restore_dedrift_brain.nii.gz`
  - If `-species` not set, `-reference` is required

## Frontend ports

- Vite dev default: 5173
- `start-notebook.sh` forces `npm run dev -- --host 0.0.0.0 --port 5173`
- Pipeline backend default: 8000
- `.env.example` includes `VITE_BACKEND_URL=http://localhost:8000`

## GUI start scripts

- `modules/gui/monkey-brain-frontend/start-notebook.sh`: runs frontend
- `modules/gui/monkey-brain-frontend/install-deps.sh`: npm install
- `modules/gui/monkey-brain-frontend/start-gui-stack.sh`: start backend + frontend
- GUI bin wrappers in `modules/gui/bin/`

## Known caveats

- Backend tasks stored in-memory (restart clears state)
- No log streaming endpoint yet
- If remote server: forward 5173 and backend port

## Recent UI notes

- Pipeline page scroll fixed with `overflow-y-auto`
- Output dir rule emphasized in UI
