"""Host-owned, versioned records. This directory is never a sandbox mount."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import threading

_LOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def checked(path):
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError("Control state must not contain symlinks")
    return path


class ControlStore:
    def __init__(self, root: Path, forbidden: list[Path]):
        self.root = checked(Path(root).absolute())
        for other in forbidden:
            other = Path(other).resolve()
            if (
                self.root == other
                or self.root.is_relative_to(other)
                or other.is_relative_to(self.root)
            ):
                raise ValueError("Protected control state overlaps a sandbox mount")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _GUARD:
            self._lock = _LOCKS.setdefault(str(self.root), threading.RLock())

    def path(self, name):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,120}", name) or name.startswith("."):
            raise ValueError("Plain control record name required")
        return checked(self.root / name)

    @contextmanager
    def locked(self):
        with self._lock:
            descriptor = os.open(
                self.path("control.lock"),
                os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            try:
                if os.name == "posix":
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            finally:
                os.close(descriptor)

    def read(self, name):
        path = self.path(name)
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Invalid control record")
        return json.loads(path.read_bytes())

    def create(self, name, value):
        raw = canonical(value)
        descriptor = os.open(
            self.path(name),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    def versions(self, kind):
        return sorted(self.root.glob(kind + ".v[0-9][0-9][0-9][0-9][0-9][0-9].json"))

    def latest(self, kind):
        paths = self.versions(kind)
        if not paths:
            return None
        value = self.read(paths[-1].name)
        if value["sha256"] != digest(value["record"]):
            raise ValueError("Protected record digest mismatch")
        return value

    def save(self, kind, record):
        with self.locked():
            version = len(self.versions(kind)) + 1
            value = {"version": version, "sha256": digest(record), "record": record}
            self.create(f"{kind}.v{version:06d}.json", value)
        return value
