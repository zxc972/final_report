"""Shared data navigation and subject discovery, independent of output location."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import re
import stat
import time
from pathlib import Path
from typing import Any

MAX_SCAN_ENTRIES = 30_000
MAX_SCAN_SECONDS = 8
MAX_TEXT_BYTES = 256_000
PRIVATE_NAMES = {".env", ".auth.json", "license.txt", "credentials.json"}
TEXT_SUFFIXES = {".csv", ".tsv", ".json", ".txt", ".md", ".py", ".log",
                 ".yaml", ".yml", ".sh", ".stats", ".lut", ".bval", ".bvec"}


def checked_path(path: Path) -> Path:
    path = path.expanduser().absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Paths must not traverse parents or symlinks")
    return path.resolve()


def read_regular(path: Path, root: Path, limit: int) -> bytes:
    """Open through directory descriptors so replaced symlinks/FIFOs cannot escape."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptors = []
    try:
        if os.open in os.supports_dir_fd:
            directory = os.open(root, flags | os.O_DIRECTORY)
            descriptors.append(directory)
            for part in path.relative_to(root).parts[:-1]:
                directory = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
                descriptors.append(directory)
            fd = os.open(path.name, flags, dir_fd=directory)
        else:
            checked_path(path)
            fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("Expected a regular file")
            return handle.read(limit)
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


class DataTools:
    def __init__(self, workspace: Path, input_roots: list[Path], workdir: Path | None = None):
        self.workspace = checked_path(workspace)
        self.input_roots = [checked_path(p) for p in input_roots]
        self.workdir = checked_path(workdir) if workdir else self.workspace
        self.roots = list(dict.fromkeys([self.workdir, *self.input_roots]))

    def resolve(self, path: str) -> Path:
        if not path or "\x00" in path or ".." in Path(path).parts:
            raise ValueError("Invalid path")
        if path == "/work" or path.startswith("/work/"):
            candidate = self.workdir / path.removeprefix("/work").lstrip("/")
        elif path.startswith("/inputs/"):
            values = path.split("/")
            if len(values) < 3 or not values[2].isdigit() or int(values[2]) >= len(self.input_roots):
                raise ValueError("Unknown input mapping")
            candidate = self.input_roots[int(values[2])] / "/".join(values[3:])
        else:
            candidate = Path(path).expanduser()
            if not candidate.is_absolute():
                candidate = self.workdir / candidate
        candidate = checked_path(candidate)
        root = next((p for p in self.roots if candidate == p or p in candidate.parents), None)
        if root is None:
            raise ValueError("Path is outside registered data roots; use list_roots to see available directories")
        if any(p.startswith(".") or p in PRIVATE_NAMES for p in candidate.relative_to(root).parts):
            raise ValueError("Hidden/private paths are not data inputs")
        return candidate

    def list_roots(self) -> dict[str, Any]:
        """List actual server data directories, input mappings and separate output directory."""
        return {"status": "ok", "outputDirectory": str(self.workspace),
                "workDirectory": str(self.workdir), "roots": [
                    {"path": str(p), "mappedPath": f"/inputs/{i}", "readOnly": True}
                    for i, p in enumerate(self.input_roots)]}

    def ls(self, path: str = "/inputs", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        """List directory entries with pagination; accepts real registered paths or /inputs/N."""
        if path == "/inputs":
            return self.list_roots()
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            children = [p for p in self.input_roots if p.parent == candidate]
            if children and not any(candidate == p or p in candidate.parents for p in self.roots):
                return {"status": "ok", "path": str(candidate), "entries": [
                    {"name": p.name, "path": str(p), "type": "directory", "readOnly": True}
                    for p in children], "nextOffset": None, "scope": "registered_data_directories"}
        directory = self.resolve(path)
        if not directory.is_dir():
            raise ValueError("Expected a directory")
        entries = []
        offset, limit = max(0, offset), max(1, min(limit, 200))
        examined = 0
        with os.scandir(directory) as scan:
            for entry in scan:
                if entry.name.startswith(".") or entry.name in PRIVATE_NAMES or entry.is_symlink():
                    continue
                if examined >= offset:
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode):
                        entries.append({"name": entry.name, "path": str(directory / entry.name),
                                        "type": "directory" if stat.S_ISDIR(info.st_mode) else "file",
                                        "size": info.st_size})
                examined += 1
                if len(entries) > limit:
                    break
        return {"status": "ok", "path": str(directory), "entries": entries[:limit],
                "nextOffset": offset + limit if len(entries) > limit else None}

    def _walk(self, directory: Path, max_depth: int, state: dict):
        started = time.monotonic()
        stack = [(directory, 0)]
        state.update(scanned=0, truncated=False)
        while stack:
            parent, depth = stack.pop()
            try:
                with os.scandir(parent) as scan:
                    for entry in scan:
                        state["scanned"] += 1
                        if state["scanned"] > MAX_SCAN_ENTRIES or time.monotonic() - started > MAX_SCAN_SECONDS:
                            state["truncated"] = True
                            return
                        if entry.name.startswith(".") or entry.name in PRIVATE_NAMES or entry.is_symlink():
                            continue
                        path = parent / entry.name
                        # A directory can change during a scan; recheck its original path.
                        self.resolve(str(path))
                        if entry.is_dir(follow_symlinks=False):
                            if depth < max_depth:
                                stack.append((path, depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            yield path
            except (OSError, ValueError):
                continue

    def glob(self, pattern: str = "*.nii*", path: str = "/inputs", max_depth: int = 10,
             limit: int = 200) -> dict[str, Any]:
        """Find filenames/relative paths recursively using wildcard patterns, without copying data."""
        if len(pattern) > 256 or ".." in Path(pattern).parts:
            raise ValueError("Invalid glob pattern")
        roots = self.input_roots if path == "/inputs" else [self.resolve(path)]
        matches, states = [], []
        limit = max(1, min(limit, 500))
        for root in roots:
            state = {}; states.append(state)
            for item in self._walk(root, max(0, min(max_depth, 16)), state):
                if fnmatch.fnmatchcase(item.name, pattern) or fnmatch.fnmatchcase(item.relative_to(root).as_posix(), pattern):
                    matches.append(str(item))
                    if len(matches) >= limit:
                        state["truncated"] = True
                        break
            if len(matches) >= limit:
                break
        return {"status": "ok", "matches": matches, "truncated": any(s.get("truncated") for s in states),
                "scanned": sum(s.get("scanned", 0) for s in states)}

    def read_file(self, path: str, start_line: int = 1, max_lines: int = 100) -> dict[str, Any]:
        """Read text/code/log/stats with line numbers; binary images are inspected in Python."""
        source = self.resolve(path)
        if source.suffix.lower() not in TEXT_SUFFIXES:
            raise ValueError("Expected text/code/table/log; inspect binary images using Python")
        root = next(p for p in self.roots if source == p or p in source.parents)
        data = read_regular(source, root, MAX_TEXT_BYTES + 1)
        if b"\x00" in data:
            raise ValueError("Binary file")
        lines = data[:MAX_TEXT_BYTES].decode("utf-8", "replace").splitlines()
        start, count = max(1, min(start_line, 100_000)), max(1, min(max_lines, 300))
        chosen = lines[start - 1:start - 1 + count]
        return {"status": "ok", "path": str(source), "startLine": start,
                "content": "\n".join(f"{i}: {line[:1000]}" for i, line in enumerate(chosen, start))[:12_000],
                "truncated": len(data) > MAX_TEXT_BYTES or len(lines) > start - 1 + count}

    def grep(self, pattern: str, path: str = "/inputs", file_pattern: str = "*",
             ignore_case: bool = False, limit: int = 50) -> dict[str, Any]:
        """Search a literal string in text/code/log/stats; bounded recursive grep with line numbers."""
        if not pattern or len(pattern) > 500:
            raise ValueError("Supply a literal search string of 1–500 characters")
        roots = self.input_roots if path == "/inputs" else [self.resolve(path)]
        matches, total_bytes, scanned = [], 0, 0
        truncated = False
        limit = max(1, min(limit, 100))
        needle = pattern.casefold() if ignore_case else pattern
        for root in roots:
            state = {}
            files = [root] if root.is_file() else self._walk(root, 10, state)
            for source in files:
                if source.suffix.lower() not in TEXT_SUFFIXES or not fnmatch.fnmatchcase(source.name, file_pattern):
                    continue
                try:
                    anchor = next(p for p in self.roots if source == p or p in source.parents)
                    data = read_regular(source, anchor, MAX_TEXT_BYTES + 1)
                except (OSError, ValueError):
                    continue
                total_bytes += len(data); scanned += 1
                if total_bytes > 8_000_000 or scanned > 1000:
                    truncated = True
                    break
                if b"\x00" in data:
                    continue
                for number, line in enumerate(data[:MAX_TEXT_BYTES].decode("utf-8", "replace").splitlines(), 1):
                    if needle in (line.casefold() if ignore_case else line):
                        matches.append({"path": str(source), "line": number, "text": line[:500]})
                        if len(matches) >= limit:
                            break
                truncated |= len(data) > MAX_TEXT_BYTES
                if len(matches) >= limit:
                    truncated = True
                    break
            truncated |= state.get("truncated", False)
            if len(matches) >= limit or total_bytes > 8_000_000 or scanned > 1000:
                break
        return {"status": "ok", "matches": matches, "scannedFiles": scanned, "truncated": truncated}

    def discover_subjects(self, path: str = "/inputs", limit: int = 100,
                          max_depth: int = 12) -> dict[str, Any]:
        """Discover BIDS, subject/T1, and flat NIfTI T1 candidates; ambiguous scans remain explicit."""
        found = self.glob("*.nii*", path, max_depth, 500)
        groups: dict[str, dict] = {}
        excluded = {"brain", "brain_mask", "wm", "mask", "T1_1mm", "T1_truncate", "T1_process_1"}
        for value in dict.fromkeys(found["matches"]):
            p = Path(value)
            source_root = next(r for r in self.input_roots + [self.workdir]
                               if p == r or r in p.parents)
            relative_parts = p.relative_to(source_root).parts
            stem = p.name.removesuffix(".gz").removesuffix(".nii")
            if not p.name.endswith((".nii", ".nii.gz")) or stem in excluded:
                continue
            if any(x.lower() in {"derivatives", "mri", "surf", "tmp", "orig", "n4_t1"} for x in relative_parts):
                continue
            if any(x in stem.lower() for x in ["t2w", "flair", "bold", "dwi", "mask", "segmentation"]):
                continue
            subject_parts = [x for x in p.parts[:-1] if re.fullmatch(r"sub-[A-Za-z0-9]+", x)]
            session_parts = [x for x in p.parts[:-1] if re.fullmatch(r"ses-[A-Za-z0-9]+", x)]
            if subject_parts:
                subject = subject_parts[-1] + ("_" + session_parts[-1] if session_parts else "")
                marker = p.parts.index(subject_parts[-1])
                key = str(Path(*p.parts[:marker + 1])) + "|" + "_".join(session_parts)
                confidence = "T1w" if "t1w" in stem.lower() else "NIfTI_candidate"
            elif p.parent.name.lower() in {"t1", "anat"}:
                subject = p.parent.parent.name
                key = str(p.parent.parent)
                confidence = "T1_directory"
            else:
                subject = re.sub(r"(?i)([_-]T1w|[_-]T1)$", "", stem)
                if subject.lower() == "t1":
                    subject = p.parent.name
                key = str(p.parent / subject)
                confidence = "filename_candidate"
            identifier = re.sub(r"[^A-Za-z0-9_-]", "_", subject).strip("_-")[:64] or "subject"
            record = groups.setdefault(key, {"candidateId": hashlib.sha256(key.encode()).hexdigest()[:16],
                "subjectId": identifier, "t1Candidates": [], "evidence": confidence,
                "species": None})
            record["t1Candidates"].append(value)
        records = list(groups.values())
        counts = {r["subjectId"]: sum(o["subjectId"] == r["subjectId"] for o in records) for r in records}
        for r in records:
            if counts[r["subjectId"]] > 1:
                r["subjectId"] += "_" + r["candidateId"][:6]
            r["ambiguous"] = len(r["t1Candidates"]) != 1
        size = max(1, min(limit, 200))
        return {"status": "ok", "subjects": records[:size], "count": len(records),
                "truncated": found["truncated"] or len(records) > size,
                "note": "Candidates need modality/species confirmation from dataset metadata or the user; discovery does not submit jobs."}
