"""Identity-scoped input roots and business context for the analysis service."""
import os
from pathlib import Path


def public_context(context: dict | None) -> dict:
    """Only business fields enter model prompts; authentication never does."""
    allowed = {"workspaceDirectory", "userId", "modelDir", "description",
               "maxConcurrentTasks", "threads", "subjectId", "species"}
    result = {key: value for key, value in (context or {}).items()
              if key in allowed and isinstance(value, (str, int, float, bool, type(None)))}
    upload = (context or {}).get("recentUpload")
    if isinstance(upload, dict):
        result["recentUpload"] = {k: v for k, v in upload.items()
            if k in {"fileName", "subjectId", "t1Path", "inputDir", "userId", "uploadedAt"}
            and isinstance(v, str)}
    return result


def analysis_workspace(workspace: str, user_id: str) -> Path:
    raw = Path(workspace).expanduser().absolute()
    resolved = raw.resolve()
    if raw != resolved or resolved.name != "output" or resolved.parent.name != user_id:
        raise ValueError("Analysis workspace must be <workspaceRoot>/<userId>/output without symlinks")
    if len(resolved.parts) < 4:
        raise ValueError("Analysis workspace is too broad")
    return resolved


def approved_input_roots(workspace: Path, requested: list[str] | None) -> list[Path]:
    """Client paths may narrow operator grants, never expand them."""
    # Never mount the ancestor of writable .analysis_runs as an input.
    candidates = [workspace.parent / "input"]
    if workspace.is_dir():
        candidates += [p for p in workspace.iterdir()
                       if not p.name.startswith('.') and p.is_dir() and not p.is_symlink()]
    grants = os.getenv("AGENT_DATA_ROOTS", os.getenv("AGENT_ANALYSIS_DATA_ROOTS", ""))
    candidates += [Path(p).expanduser() for p in grants.split(os.pathsep) if p]
    # Operator-designated data home: discover new dataset folders on every request.
    # No per-dataset code changes, input copies or output-directory coupling.
    data_home = os.getenv("AGENT_DATA_DIRECTORY", "")
    excluded = set(os.getenv("AGENT_DATA_EXCLUDE_DIRS", "agent:structural_env").split(os.pathsep))
    if data_home:
        home_path = Path(data_home).expanduser().absolute()
        if any(p.is_symlink() for p in (home_path, *home_path.parents)):
            raise ValueError("Data home must not contain symlinks")
        if home_path.is_dir():
            candidates += [p for p in home_path.iterdir() if p.is_dir() and not p.is_symlink()
                           and not p.name.startswith('.') and p.name not in excluded
                           and not (p/'.auth.json').exists()
                           and p != workspace and p not in workspace.parents]
    def checked_directory(path: Path) -> Path:
        absolute = path.absolute()
        # Check the original path before resolving: resolving a user's input
        # symlink first would silently turn its target into a new grant.
        if any(part.is_symlink() for part in (absolute, *absolute.parents)):
            raise ValueError("Input roots must not contain symlinks")
        return absolute.resolve()

    allowed = [checked_directory(p) for p in candidates if p.is_dir()]
    result = []
    for p in ([Path(s).expanduser() for s in requested] if requested is not None else allowed):
        resolved = checked_directory(p)
        if (resolved == workspace or not resolved.is_dir()
                or not any(resolved == a or a in resolved.parents for a in allowed)):
            raise ValueError("Input root is outside the user's data or configured shared datasets")
        if resolved not in result:
            result.append(resolved)
    return result
