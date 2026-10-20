"""Verify the original server snapshot without loading agent dependencies."""
from pathlib import Path
import hashlib
import gzip
import json

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "SNAPSHOT_MANIFEST.json").read_text(encoding="utf-8"))
errors = []
for entry in manifest["files"]:
    if "archive_path" not in entry:
        continue
    archive = (root / entry["archive_path"]).resolve()
    target = (root / entry["path"]).resolve()
    if not archive.is_relative_to(root) or not target.is_relative_to(root) or not archive.is_file():
        raise SystemExit("Invalid graph archive path")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != entry["archive_sha256"]:
        raise SystemExit("Graph archive checksum mismatch")
    with gzip.open(archive, "rb") as handle:
        raw = handle.read(entry["bytes"] + 1)
    if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise SystemExit("Unpacked graph differs from server snapshot")
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
for entry in manifest["files"]:
    path = (root / entry["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        errors.append(entry["path"] + ": missing or outside root")
        continue
    raw = path.read_bytes()
    if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        errors.append(entry["path"] + ": differs from server snapshot")
release = root / "knowledge/research_v13"
config = json.loads((release / "config.json").read_text(encoding="utf-8"))
for name, digest in config.get("snapshot_files", {}).items():
    path = (release / name).resolve()
    if not path.is_relative_to(release) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        errors.append("research release: " + name)
if errors:
    raise SystemExit("\n".join(errors))
print(f"Verified {len(manifest['files'])} source files and {len(config.get('snapshot_files', {}))} research-release digests.")
