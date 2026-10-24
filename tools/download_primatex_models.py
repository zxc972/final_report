"""Download public, revision-pinned rhesus assets and verify official hashes."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time
import urllib.request

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument(
    "--assets",
    type=Path,
    default=Path(__file__).resolve().parents[1]
    / "docs/round15/PRIMATEX_RHESUS_MODELS.json",
)
PARSER.add_argument(
    "--output",
    type=Path,
    required=True,
    help="PrimateX modules/primx_seg/models directory",
)
ARGS = PARSER.parse_args()
ROOT = ARGS.output.resolve()
ROOT.mkdir(parents=True, exist_ok=True)
INDEX = json.loads(ARGS.assets.read_text(encoding="utf-8-sig"))


def fetch(asset):
    relative = asset["path"]
    target = ROOT / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Unsafe model asset path")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    url = (
        "https://huggingface.co/CNAIL/PrimateX/resolve/"
        + INDEX["commit"]
        + "/"
        + relative
        + "?download=true"
    )
    result = {"path": relative, "expected_bytes": asset["size"]}
    for attempt in range(3):
        try:
            if not target.exists():
                start = partial.stat().st_size if partial.exists() else 0
                headers = {"Range": f"bytes={start}-"} if start else {}
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers=headers), timeout=60
                ) as response:
                    with partial.open(
                        "ab" if start and response.status == 206 else "wb"
                    ) as stream:
                        while chunk := response.read(4 * 1024 * 1024):
                            stream.write(chunk)
                if partial.stat().st_size != asset["size"]:
                    raise ValueError("Downloaded size differs from official tree")
                partial.rename(target)
            digest = hashlib.sha256()
            git_digest = hashlib.sha1()
            git_digest.update(f"blob {target.stat().st_size}\0".encode())
            with target.open("rb") as stream:
                while chunk := stream.read(4 * 1024 * 1024):
                    digest.update(chunk)
                    git_digest.update(chunk)
            expected = asset.get("lfs")
            valid = (
                digest.hexdigest() == expected["oid"]
                if expected
                else git_digest.hexdigest() == asset["oid"]
            )
            if target.stat().st_size != asset["size"] or not valid:
                raise ValueError("Official hash verification failed")
            result.update(status="verified", sha256=digest.hexdigest())
            if "error_type" in result:
                result["recovered_error_type"] = result.pop("error_type")
            print(json.dumps(result), flush=True)
            return result
        except Exception as error:
            result.update(status="failed", error_type=type(error).__name__)
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fetch, INDEX["assets"]))
    (ROOT / "download_verification.json").write_text(
        json.dumps(
            {"repo": INDEX["repo"], "commit": INDEX["commit"], "files": results},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    raise SystemExit(0 if all(r["status"] == "verified" for r in results) else 1)
