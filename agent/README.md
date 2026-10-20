# PrimateX Monorepo

PrimateX is a monorepo for non-human primate imaging agent-assisted workflow.
It keeps each module self-contained while exposing a unified `primx` CLI entrypoint.
Scientific processing is intended to run through a Singularity container that provides FSL, FreeSurfer, ANTs, Python, PyTorch, and related neuroimaging tools.

![PrimateX Installation Framework](Figures/FigureSI.png)

## Modules

- `modules/neuro_pipeline/`: cortical reconstruction preprocessing pipeline, FreeSurfer reconstruction helpers, rescaling, fs_LR conversion, and small Python utilities.
- `modules/primx_seg/`: deep-learning brain and white-matter segmentation.
- `modules/gui/`: React GUI plus Node.js pipeline backend for upload, pipeline orchestration, task management, logs, downloads, reports, and visualization.
- `modules/agent/`: FastAPI Workflow Assistant backend with tool-calling, skill registry, workspace isolation, sample-data tools, and configurable LLM providers.
- `modules/FastSurfer/`: FastSurfer submodule for human T1 preprocessing and reconstruction.
- `workflows/primx_cli/`: unified CLI wrapper that dispatches to the modules above.

## Installation

The repository usually stays outside the container and is mounted into the container with `singularity exec -B ...`.

You need:

- Singularity or Apptainer.
- A FreeSurfer license from the [FreeSurfer registration page](https://surfer.nmr.mgh.harvard.edu/registration.html).
- Node.js 18+ if you use the GUI.

When running FreeSurfer steps, bind the license into the container at `/opt/freesurfer-7.2.0/.license`:

```shell
-B /path/to/your/freesurfer/license.txt:/opt/freesurfer-7.2.0/.license
```

1. Clone repository

```shell
# SSH
git clone --recurse-submodules git@github.com:YCHuang0610/PrimateX.git

# Or HTTPS
git clone --recurse-submodules https://github.com/YCHuang0610/PrimateX.git

cd PrimateX
```

If you cloned without submodules:

```shell
git submodule update --init --recursive
```

2. Download Singularity container

- Container download: please contact zheng.wang@pku.edu.cn to request access.
- Example name: `PrimateX_1_X.sif`

3. Download segmentation model files

- Model download: https://huggingface.co/CNAIL/PrimateX
- Put model files under `modules/primx_seg/models/`.
- Each installed checkpoint directory must be named `<species>_<task>`, for
  example `cynomolgus_brain/` or `marmoset_wm/`.

4. Optional GUI dependencies

```shell
container=/path/to/your/container/PrimateX.sif
primx=$PWD/workflows/primx_cli/primx

singularity exec -B "$PWD":"$PWD" "$container" \
    "$primx" gui install-deps
```

## Running

### Minimal Pipeline Example Using Unified CLI

```shell
surf=/path/to/workdir
container=/path/to/your/container/PrimateX.sif
license=/path/to/your/freesurfer/license.txt
subjid=YY_T1

primx=/path/to/PrimateX/workflows/primx_cli/primx

# Step 1: preprocess T1
singularity exec -B "$surf":"$surf" "$container" \
    "$primx" neuro preprocess-1 \
    -t1_path "$surf/$subjid/T1" \
    -out_path "$surf/$subjid" \
    -species Macaque \
    -denoise

# Step 2: segmentation with ACPC alignment between brain and WM segmentation
singularity exec --nv -B "$surf":"$surf" "$container" \
    "$primx" seg brain \
    -species cynomolgus \
    -input_image "$surf/$subjid/T1.nii.gz" \
    -output_dir "$surf/$subjid"

singularity exec -B "$surf":"$surf" "$container" \
    "$primx" neuro acpc-align \
    -out_path "$surf/$subjid" \
    -brainSize 80 \
    -species Macaque

singularity exec --nv -B "$surf":"$surf" "$container" \
    "$primx" seg wm \
    -species cynomolgus \
    -input_image "$surf/$subjid/brain.nii.gz" \
    -output_dir "$surf/$subjid"

# Step 3: FreeSurfer reconstruction
singularity exec -B "$surf":"$surf" \
    -B "$license":/opt/freesurfer-7.2.0/.license \
    "$container" \
    "$primx" neuro preprocess-3 \
    -id "$subjid" \
    -out_path "$surf/$subjid" \
    -species Macaque

# Step 4: rescale and register to fs_LR
singularity exec -B "$surf":"$surf" \
    -B "$license":/opt/freesurfer-7.2.0/.license \
    "$container" \
    "$primx" neuro rescale \
    -id "$subjid" \
    -out_path "$surf/$subjid" \
    -species Macaque

singularity exec -B "$surf":"$surf" \
    -B "$license":/opt/freesurfer-7.2.0/.license \
    "$container" \
    "$primx" neuro freesurfer2caret \
    -id "$subjid" \
    -out_path "$surf/$subjid" \
    -LowResMesh 32 \
    -species Macaque
```

Important reconstruction behavior:

- `preprocess-3` accepts `-threads N` (default `1`) and passes it only to
  commands with a supported thread interface.
- Macaque and Marmoset use a warped atlas as the base `aseg`. When
  `wm.nii.gz` is available, the default hybrid mode replaces cortical WM with
  the DL result while preserving atlas subcortical labels. Use
  `-no-hybrid-aseg` for a pure-atlas comparison.
- Chimpanzee keeps its species-specific GCA segmentation route; hybrid flags
  are ignored.
- Marmoset uses a T1-only pial refinement with WM-core-weighted N4 correction
  and species-specific surface settings. Its generated candidates and QC
  table still require visual review.

See [`modules/neuro_pipeline/README.md`](modules/neuro_pipeline/README.md) for
the output variants, QC files, and species-specific details.

### GUI Startup

```shell
container=/path/to/your/container/PrimateX.sif
license=/path/to/your/freesurfer/license.txt
repo=/path/to/PrimateX
primx=$repo/workflows/primx_cli/primx

singularity exec --nv \
    -B "$repo":"$repo" \
    -B /your/workspace:/your/workspace \
    -B "$license":/opt/freesurfer-7.2.0/.license \
    "$container" \
    "$primx" gui start \
    --port 8080 \
    --pipeline-port 8000 \
    --agent-port 8100 \
    --token YOUR_TOKEN
```

`primx gui start` launches the React frontend, Node.js pipeline backend, and FastAPI agent backend together. Ports are auto-selected if the requested ports are occupied. The startup banner prints local and remote URLs in this form:

```text
http://<HOST>:<FRONTEND_PORT>/?token=<PRIMX_ACCESS_TOKEN>
```

If neither `--token` nor `PRIMX_ACCESS_TOKEN` is supplied, the development
launcher generates a fresh access token for each launch. Override
this default for any shared or externally reachable deployment.

The bundled Vite server is for local development and SSH-tunnel access only. Do not expose the Vite port directly to the public Internet. For public deployments, build the frontend and serve the generated static files through Nginx as described below.

GUI pages:

- `/dashboard`: entry page.
- `/config`: set User ID, workspace, model directory, and Workflow Assistant model provider.
- `/pipeline`: upload or select T1 data, choose pipeline steps, submit runs, inspect task history, cancel tasks, view logs, and download results.
- `/segmentation`: task-management view across Node backend tasks, agent-submitted tasks, and filesystem-derived subject status.
- `/visualization`: browse outputs, view image overlays, generate HTML reports, and open reports.
- `/agent`: Workflow Assistant for natural-language pipeline control.

The GUI uses this workspace convention:

```text
workspace/<userId>/input/<subjectId>/T1/
workspace/<userId>/output/<subjectId>/
```

Set a unique User ID before uploading data or launching runs. This is required for per-user isolation and predictable task visibility.
User IDs are restricted to 3-32 path-safe characters; Subject IDs use 1-32
characters. Both allow only letters, numbers, underscore, or dash and must
start with a letter or number.

The Pipeline page binds uploaded and sample-derived T1 paths to the Subject ID
that selected them. Changing the Subject ID clears a managed path belonging to
the old subject, while an explicitly entered path outside the managed
workspace is preserved. The backend revalidates the binding on submission.

`maxConcurrentTasks` controls how many Agent pipelines may progress at once.
The separate Preprocess-3 CPU thread setting is limited to 1-4 threads per
task. Deep-learning `seg-brain` and `seg-wm` subprocesses share one
step-scoped execution slot to avoid memory/BLAS pressure; preprocessing,
alignment, reconstruction, and export steps can continue concurrently.
`Waiting for segmentation resource` is therefore an expected cancellable
state. Agent-submitted tasks appear in Task Management with their logs and
cancel action.

For a public website, serve the built frontend through Nginx and proxy only API routes to the local backends:

```shell
cd /path/to/PrimateX/modules/gui/monkey-brain-frontend
npm install
npm run build
```

Example Nginx site configuration:

```nginx
server {
    listen 80;
    server_name primatex.pku.edu.cn;

    root /path/to/PrimateX/modules/gui/monkey-brain-frontend/dist;
    index index.html;

    # Choose a limit appropriate for your expected NIfTI uploads.
    client_max_body_size 2048m;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/agent/ {
        proxy_pass http://127.0.0.1:8100;
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

Reload Nginx after editing the site config, for example `sudo nginx -t && sudo systemctl reload nginx`. Keep ports `8080`, `8000`, and `8100` closed to public clients; the backends should listen on `127.0.0.1` and be reached through Nginx.

If large T1 uploads fail with `413 Request Entity Too Large`, increase `client_max_body_size` in the PrimateX Nginx server block. Large result downloads are streamed from the backend as `.tar.gz` archives, so they are not affected by `client_max_body_size`. If large downloads stop early or time out behind Nginx, increase the API proxy timeouts and keep response buffering disabled for the API routes.

### Workflow Assistant Models

The agent backend supports two model sources:

- Platform models: server-managed API key, model list from `modules/agent/platform_models.json`.
- Custom provider: user-supplied OpenAI-compatible `base_url`, `model`, and API key from the GUI.

To enable platform models, set the server-side environment variable before starting the GUI or agent backend:

```shell
export PLATFORM_API_KEY=<server-side-api-key>
# Optional; defaults to https://api.modelverse.cn/v1
export PLATFORM_API_BASE_URL=https://api.modelverse.cn/v1
```

If `PLATFORM_API_KEY` is unset, users can still choose the custom provider path.

### Human FastSurfer Module

FastSurfer is wrapped in `primx` for human T1 preprocessing and reconstruction:

```shell
surf=/path/to/workdir
container=/path/to/your/container/PrimateX.sif
license=/path/to/your/freesurfer/license.txt
subjid=sub_006

primx=/path/to/PrimateX/workflows/primx_cli/primx

singularity exec --nv -B "$surf":"$surf" \
    -B "$license":/opt/freesurfer-7.2.0/.license \
    "$container" \
    "$primx" human fastsurfer \
    -t1_path "$surf/$subjid/T1/sub-006_T1w.nii.gz" \
    -id "$subjid" \
    -out_path "$surf/$subjid" \
    -threads 4
```

Notes:

- `primx human fastsurfer` appends `--ignore_fs_version` to support the current container environment.
- FastSurfer output layout is `<out_path>/<id>/...`.

## CLI Reference

| Module    | Commands                                                                                                                                                              | Notes                                                     |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `neuro` | `preprocess-1`, `preprocess-3`, `preprocess-3-1`, `preprocess-3-2`, `rescale`, `freesurfer2caret`, `acpc-align`, `label-resample`, `image-reorient` | Non-human primate reconstruction workflow and utilities.  |
| `seg`   | `brain`, `wm`, `router`                                                                                                                                         | Deep-learning segmentation and species/image router.      |
| `human` | `fastsurfer`                                                                                                                                                        | Human T1 FastSurfer wrapper.                              |
| `gui`   | `install-deps`, `start`                                                                                                                                           | GUI stack with frontend, Node backend, and agent backend. |
| `agent` | `start-agent-backend`                                                                                                                                               | Standalone Workflow Assistant backend.                    |

Notes for `primx`:

- `primx --log_dir <dir> ...` writes command logs through `tee`.
- `primx seg brain|wm` defaults `-model_dir` to `modules/primx_seg/models` when omitted.
- `primx seg router` routes an input image to the appropriate segmentation command.
- `primx neuro preprocess-3` runs the split FreeSurfer steps `preprocess-3-1` then `preprocess-3-2`.
- `primx neuro preprocess-3-1` and `primx neuro preprocess-3-2` remain available for manual staged execution.
- `primx neuro image-reorient` reorients images to a requested orientation.
- `primx neuro label-resample` resamples label images with nearest-neighbor interpolation.
- `primx gui start [--port N] [--pipeline-port N] [--agent-port N] [--token TOKEN]` starts all GUI services.
- Detailed neuro command options are documented in `modules/neuro_pipeline/README.md`.

## Ports, Token Auth, and Runtime Discovery

The GUI and backends auto-select free ports to avoid collisions on shared servers. The chosen ports are written to:

```text
modules/gui/monkey-brain-frontend/public/ports.json
```

Example:

```json
{
  "pipelinePort": "8000",
  "agentPort": "8100",
  "frontendPort": "8080"
}
```

Access is token-gated. Provide a token with `--token`, or set `PRIMX_ACCESS_TOKEN`.
The GUI launcher has the development default described above; the standalone
backends disable this bearer-token check only when the variable is empty.

## Help / Docs

- Neuro pipeline toolkit: `modules/neuro_pipeline/README.md`
- Segmentation usage: `modules/primx_seg/readme.txt`
- GUI frontend notes: `modules/gui/monkey-brain-frontend/README.md`
- Pipeline backend notes: `modules/gui/monkey-brain-backend/README.md`
- Agent backend notes: `modules/agent/README.md`

## Notes

- If you use software included in the container, cite the relevant papers and obtain licenses when required.
- FreeSurfer tools require a valid license file. See the [FreeSurfer registration page](https://surfer.nmr.mgh.harvard.edu/registration.html).

## Citation

If you use PrimateX in academic work, please cite:

Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.<br>
*Multi-agentic routing with PrimateX: standardized structural MRI analysis for non-human primates and humans.*

- `*` Equal contribution.
- `#` Correspondence: Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang (zheng.wang@pku.edu.cn).

See [`CITATION.cff`](CITATION.cff) for full citation details.

## License

PrimateX is licensed under the GNU Affero General Public License v3.0. See [`LICENSE`](LICENSE) for the complete terms. If you distribute PrimateX or a derivative work under the AGPL license, you must provide the corresponding source code under the same license and preserve applicable copyright and license notices.

Comprehensive commercial/proprietary licensing of PrimateX is available separately, please contact zheng.wang@pku.edu.cn.

PrimateX includes or interfaces with third-party software, code, and data resources that remain subject to their own license terms. Those third-party licenses are not replaced by the PrimateX license. See [`THIRD_PARTY_NOTICES.md`](docs/THIRD_PARTY_NOTICES.md) for known third-party notices.
