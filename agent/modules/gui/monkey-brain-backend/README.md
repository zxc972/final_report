# Monkey Brain Pipeline Backend

This backend provides `/api/pipeline/*` endpoints for the GUI pipeline page.
It runs `primx` commands on the same host and writes logs to `<out_path>/logs`.

## Run

```bash
node server.js
```

Environment:
- `PIPELINE_PORT` (default: 8000)
- `PRIMX_PATH` (default: `<repo>/workflows/primx_cli/primx`)
