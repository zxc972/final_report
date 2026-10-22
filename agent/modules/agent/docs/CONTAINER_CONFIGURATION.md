# Trusted container configuration

The default engine is still `apptainer`. Operators may select a compatible
executable and relocate the image/runtime with these host settings:

| Variable | Default |
| --- | --- |
| `ANALYSIS_CONTAINER_CMD` | `apptainer` |
| `ANALYSIS_RUNTIME_IMAGE` | `/data/xuancheng/agent/PrimateX_1_7.sif` |
| `ANALYSIS_RUNTIME_ENV` | `/data/xuancheng/structural_env/runtime/python-analysis` |

Explicit `runtime_image`, `runtime_env`, and legacy `apptainer_binary` constructor
arguments take precedence. The command variable names one executable, not a shell
command with arguments. PATH lookup occurs before the child receives its minimal
`PATH=/usr/bin:/bin`; `/usr/local/bin/singularity` therefore works without adding
host paths to the isolated environment. Empty settings fail closed.

## Execution policy

| Command component | Required purpose |
| --- | --- |
| `exec --cleanenv` | Clear inherited container environment |
| `--containall --no-home` | Isolate filesystem/PID/environment; omit host home |
| `--no-mount bind-paths,hostfs,cwd,tmp` | Suppress default system binds, host filesystem, cwd and tmp mounts |
| `--net --network none` | Distinct network namespace without external networking |
| `--pwd /work` | Dedicated working directory |
| `--bind <work>:/work:rw` | The only writable host mount; frozen verification can request `ro` |
| `--bind <runtime>:/opt/analysis:ro` | Immutable scientific Python runtime |
| `--bind <input>:/inputs/<i>:ro` | Read-only approved inputs |
| `--bind <operations>:/opt/primatex_ops.py:ro` | Optional hash-checked operation library |
| `--bind <snapshot>:/work/<target>:ro` | Optional trusted frozen source |
| Optional single FreeSurfer license-file bind, `ro` | Never expose the containing directory |
| `/usr/bin/env -i ...` | Pass only the explicit runtime environment |
| `/opt/analysis/bin/python -I -B` | Ignore inherited Python paths and suppress bytecode writes |
| Trusted `resource.setrlimit` launcher | Enforce address-space and per-file size hard limits |

Selecting a different executable does not remove or weaken these arguments.
`probe()` must pass every required isolation check before model code runs.
Unsupported options or a missing runtime remain blocked; there is no host-Python
fallback. Resource limits are per process/file, not aggregate RAM/disk quotas.

## Singularity CE 3.9 on 6007

The installed non-setuid 3.9.2 engine ignores the `bind-paths` token and unpacks a
SIF to a temporary sandbox on each invocation. A bare executable substitution is
therefore insufficient for this installation. Its environment-specific profile
is stored outside the repository under `/data/xuancheng/agent_v1/`:

- A private non-setuid Singularity configuration has **no** `bind path` entries.
  This supplies the binding guarantee missing from the unsupported token.
- A launcher validates the private configuration hash and the registered source
  SIF identity. Only then does it replace `bind-paths` with that bind-free config;
  `hostfs,cwd,tmp`, network, containment, explicit read-only mounts, and clean
  environment remain required.
- The existing SIF is unpacked once into a separate cache; empty mount targets
  are prepared there. Analysis uses it as a read-only container root to avoid
  repeated full-image unpacking. The source SIF is not rewritten.
- This profile is usable only after real network, mount, host-visibility and
  resource-limit probes pass. Its generated launcher, config hashes and actual
  test results belong in the environment audit, not in model-visible inputs.

Scientific runtime construction may use network access solely to install the
locked recipe, with no study inputs, API configuration or host license mounted.
Analysis execution continues to require `--net --network none`.
