"""Fail-closed Linux analysis execution using a read-only Apptainer image.

The security boundary is Apptainer's mount/PID/network namespaces, not Python
validation or a changed cwd. Only /work is a writable host mount. Inputs are
read-only /inputs/0, /inputs/1, ...; neither /data nor the host home is mounted.
The copied analysis venv requires the legacy image's /miniconda3 base runtime.
The trusted in-container launcher applies hard and soft RLIMIT_AS/RLIMIT_FSIZE
before running any model code. These bound each process's virtual address space
and each regular file's size; they are not aggregate memory, process or disk
quotas. Server configuration uses integer byte values, never model tool args.

Requirements: Linux, Apptainer with an allowed ``--net --network none`` policy,
the legacy SIF, and the structural_env analysis venv. No unsafe fallback exists.
The command_runner/platform_name arguments are trusted test injection points.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


DEFAULT_IMAGE = Path("/data/xuancheng/agent/PrimateX_1_7.sif")
DEFAULT_RUNTIME = Path("/data/xuancheng/structural_env/runtime/python-analysis")
DEFAULT_FS_LICENSE = Path("/data/xuancheng/license.txt")
CONTAINER_FS_LICENSE = "/opt/analysis_freesurfer_license.txt"
PROBE_MARKER = "PRIMATEX_SANDBOX_PROBE="
SUPPORTED_BACKENDS = ("apptainer",)
DEFAULT_MEMORY_BYTES = 8 * 1024 ** 3
DEFAULT_FILE_BYTES = 1024 ** 3

_LIMIT_LAUNCHER = '''import resource, runpy, sys
def apply_limit(kind, requested):
    previous_hard = resource.getrlimit(kind)[1]
    effective = requested if previous_hard == resource.RLIM_INFINITY else min(requested, previous_hard)
    resource.setrlimit(kind, (effective, effective))
apply_limit(resource.RLIMIT_AS, int(sys.argv[1]))
apply_limit(resource.RLIMIT_FSIZE, int(sys.argv[2]))
arguments = sys.argv[3:]
if arguments[0] == "-c":
    exec(compile(arguments[1], "<trusted-sandbox-probe>", "exec"), {"__name__": "__main__"})
else:
    sys.argv = arguments
    runpy.run_path(arguments[0], run_name="__main__")
'''


def _configured_limit(value: int | None, variable: str, default: int) -> int:
    if value is None:
        raw = os.environ.get(variable)
        try:
            value = int(raw) if raw is not None else default
        except ValueError as exc:
            raise ValueError(f"{variable} must be an integer byte count") from exc
    if type(value) is not int or not 1 <= value <= 2 ** 60:
        raise ValueError(f"{variable} must be a positive bounded integer byte count")
    return value


def _no_symlink_components(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"Symlink path components are not allowed: {component}")


def _absolute_path(path: Path) -> Path:
    if ".." in path.parts:
        raise ValueError("Parent traversal is not allowed")
    result = path.absolute()
    _no_symlink_components(result)
    return result


def _overlap(a: Path, b: Path) -> bool:
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _mount_spec(source: Path, destination: str, mode: str) -> str:
    value = str(source)
    # These characters are syntax in Apptainer's bind-list grammar.
    if any(c in value for c in (",", "\n", "\r", "\x00")) or (
        ":" in value and not source.drive
    ):
        raise ValueError("Unsupported character in a mount source path")
    return f"{value}:{destination}:{mode}"


class _BoundedBytes:
    def __init__(self, limit: int):
        self.limit = limit
        self.data = bytearray()
        self.total = 0

    def read_from(self, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                self.total += len(chunk)
                remaining = self.limit - len(self.data)
                if remaining > 0:
                    self.data.extend(chunk[:remaining])
        except (OSError, ValueError):
            pass
        finally:
            stream.close()

    def text(self) -> str:
        return bytes(self.data).decode("utf-8", errors="replace")


def _terminate_group(process: subprocess.Popen[bytes]) -> None:
    """Terminate the entire launch group, including container descendants."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        elif process.poll() is None:
            process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    # The group leader can exit before a descendant; still signal the group.
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _run_bounded(
    command: list[str], *, timeout_seconds: int, env: dict[str, str],
    output_limit_bytes: int,
) -> dict[str, Any]:
    stdout, stderr = _BoundedBytes(output_limit_bytes), _BoundedBytes(output_limit_bytes)
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, start_new_session=(os.name == "posix"),
        )
    except OSError as exc:
        return {"exit_code": None, "stdout": "", "stderr": str(exc)[:output_limit_bytes],
                "timed_out": False, "stdout_truncated": False, "stderr_truncated": False}
    readers = [threading.Thread(target=buffer.read_from, args=(stream,), daemon=True)
               for buffer, stream in ((stdout, process.stdout), (stderr, process.stderr))]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_group(process)
    except BaseException:
        # Cancellation must reap this isolated process group, never leave MRI
        # commands orphaned after their owner worker has exited.
        _terminate_group(process)
        for reader in readers:
            reader.join(timeout=1)
        raise
    for reader in readers:
        reader.join(timeout=1)
    if any(reader.is_alive() for reader in readers):
        _terminate_group(process)
        for reader in readers:
            reader.join(timeout=1)
    return {"exit_code": process.poll(), "stdout": stdout.text(), "stderr": stderr.text(),
            "timed_out": timed_out, "stdout_truncated": stdout.total > stdout.limit,
            "stderr_truncated": stderr.total > stderr.limit}


class SandboxExecutor:
    def __init__(
        self, workdir: Path, input_roots: list[Path], *, backend: str = "apptainer",
        runtime_image: Path = DEFAULT_IMAGE, runtime_env: Path = DEFAULT_RUNTIME,
        apptainer_binary: str | Path = "apptainer", output_limit_bytes: int = 16000,
        memory_limit_bytes: int | None = None, file_size_limit_bytes: int | None = None,
        command_runner: Callable[..., dict[str, Any]] | None = None,
        platform_name: str | None = None,
        fs_license_file: Path | None = None,
    ) -> None:
        self.workdir = _absolute_path(Path(workdir))
        if len(self.workdir.parts) < 3:
            raise ValueError("A dedicated work directory is required")
        self.input_roots = [_absolute_path(Path(p)) for p in input_roots]
        if len(self.input_roots) > 32:
            raise ValueError("At most 32 input roots are allowed")
        for root in self.input_roots:
            if len(root.parts) < 3 or not root.is_dir():
                raise ValueError("Input roots must be existing dedicated directories")
            if _overlap(root, self.workdir):
                raise ValueError("Input roots must not overlap the writable work directory")
        self.runtime_image = Path(runtime_image).resolve()
        self.runtime_env = Path(runtime_env).resolve()
        if _overlap(self.workdir, self.runtime_env) or self.runtime_image.is_relative_to(self.workdir):
            raise ValueError("The writable work directory must not expose the runtime assets")
        # Only the existing FreeSurfer license file is an additional runtime
        # asset. Never mount its parent directory or inherit provider secrets.
        selected_license = fs_license_file
        if (selected_license is None and self.runtime_image == DEFAULT_IMAGE.resolve()
                and DEFAULT_FS_LICENSE.is_file()):
            selected_license = DEFAULT_FS_LICENSE
        self.fs_license_file = (_absolute_path(Path(selected_license))
                                if selected_license is not None else None)
        if self.fs_license_file is not None:
            self._validate_license()
        self.backend = backend
        self.apptainer_binary = str(apptainer_binary)
        if not isinstance(output_limit_bytes, int) or not 1024 <= output_limit_bytes <= 1048576:
            raise ValueError("output_limit_bytes must be between 1024 and 1048576")
        self.output_limit_bytes = output_limit_bytes
        self.memory_limit_bytes = _configured_limit(memory_limit_bytes,
            "AGENT_ANALYSIS_MEMORY_BYTES", DEFAULT_MEMORY_BYTES)
        self.file_size_limit_bytes = _configured_limit(file_size_limit_bytes,
            "AGENT_ANALYSIS_FILE_BYTES", DEFAULT_FILE_BYTES)
        self.operations_source = None
        self.operations_sha256 = None
        self._runner = command_runner or _run_bounded
        self._platform = platform_name or sys.platform
        # Validate bind grammar before creating anything.
        for source in [self.workdir, self.runtime_env, *self.input_roots]:
            _mount_spec(source, "/validation", "ro")
        self.workdir.mkdir(parents=True, exist_ok=True)
        if not self.workdir.is_dir():
            raise ValueError("workdir must be a directory")

    def enable_operations(self, source: Path, sha256: str) -> None:
        """Trusted host-only configuration; never accepts model arguments."""
        import hashlib
        source = _absolute_path(source)
        if (not source.is_file() or source.suffix != ".py"
                or not 0 < source.stat().st_size <= 96_000
                or _overlap(source, self.workdir)
                or hashlib.sha256(source.read_bytes()).hexdigest() != sha256):
            raise ValueError("Invalid read-only operation asset")
        self.operations_source = source
        self.operations_sha256 = sha256

    def _validate_license(self) -> None:
        path = self.fs_license_file
        if path is None:
            return
        _no_symlink_components(path)
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 16384
                or _overlap(path, self.workdir)):
            raise ValueError("FreeSurfer license must be a small existing runtime file outside /work")
        _mount_spec(path, CONTAINER_FS_LICENSE, "ro")

    @staticmethod
    def available_backends() -> list[str]:
        return list(SUPPORTED_BACKENDS)

    def _environment(self) -> dict[str, str]:
        # No inherited API keys, proxy variables, Python path, HOME or bind paths.
        return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": "/tmp"}

    def _command(self, workdir: Path, inputs: list[Path], python_args: list[str], *,
                 frozen_source: Path | None = None, frozen_target: str | None = None,
                 work_read_only: bool = False) -> list[str]:
        command = [self.apptainer_binary, "exec", "--cleanenv", "--containall", "--no-home",
                   "--no-mount", "bind-paths,hostfs,cwd,tmp", "--net", "--network", "none",
                   "--pwd", "/work", "--bind", _mount_spec(workdir, "/work", "ro" if work_read_only else "rw"),
                   "--bind", _mount_spec(self.runtime_env, "/opt/analysis", "ro")]
        self._validate_license()
        if self.fs_license_file is not None:
            command.extend(["--bind", _mount_spec(self.fs_license_file, CONTAINER_FS_LICENSE, "ro")])
        for i, root in enumerate(inputs):
            command.extend(["--bind", _mount_spec(root, f"/inputs/{i}", "ro")])
        if frozen_source is not None:
            snapshot = _absolute_path(Path(frozen_source))
            if (snapshot.suffix != ".py" or not snapshot.is_file()
                    or not 0 < snapshot.stat().st_size <= 100_000
                    or not isinstance(frozen_target, str) or not frozen_target.startswith("/work/")
                    or any(part in ("", ".", "..") for part in frozen_target[len("/work/"):].split("/"))
                    or any(c in frozen_target for c in "\\:,\n\r\x00")):
                raise ValueError("Invalid trusted frozen Python source binding")
            command.extend(["--bind", _mount_spec(snapshot, frozen_target, "ro")])
        launcher = _LIMIT_LAUNCHER
        if self.operations_source is not None:
            import hashlib
            if hashlib.sha256(self.operations_source.read_bytes()).hexdigest() != self.operations_sha256:
                raise ValueError("Operation library changed after run initialization")
            command.extend(["--bind", _mount_spec(self.operations_source, "/opt/primatex_ops.py", "ro")])
            trusted = ("import hashlib, pathlib\n"
                       "assert hashlib.sha256(pathlib.Path('/opt/primatex_ops.py').read_bytes()).hexdigest() == "
                       + repr(self.operations_sha256) + "\n"
                       "sys.path.insert(0, '/opt')\n")
            launcher = launcher.replace('arguments = sys.argv[3:]', trusted + 'arguments = sys.argv[3:]')
        command.extend([str(self.runtime_image), "/usr/bin/env", "-i", "HOME=/work",
                        "TMPDIR=/work", "MPLCONFIGDIR=/work/.mpl-cache", "LANG=C.UTF-8",
                        "PATH=/opt/analysis/bin:/miniconda3/bin:/usr/bin:/bin",
                        "OMP_NUM_THREADS=1", "OPENBLAS_NUM_THREADS=1",
                        *(["FS_LICENSE=" + CONTAINER_FS_LICENSE] if self.fs_license_file is not None else []),
                        "/opt/analysis/bin/python", "-I", "-B", "-c", launcher,
                        str(self.memory_limit_bytes), str(self.file_size_limit_bytes), *python_args])
        return command

    def _invoke(self, command: list[str], timeout: int) -> dict[str, Any]:
        result = self._runner(command, timeout_seconds=timeout, env=self._environment(),
                              output_limit_bytes=self.output_limit_bytes)
        # Bound results from an injected runner as well.
        for key in ("stdout", "stderr"):
            raw = str(result.get(key, "")).encode("utf-8", errors="replace")
            result[f"{key}_truncated"] = bool(result.get(f"{key}_truncated")) or len(raw) > self.output_limit_bytes
            result[key] = raw[:self.output_limit_bytes].decode("utf-8", errors="ignore")
        return result

    def probe(self) -> dict[str, Any]:
        blocked = {"status": "blocked", "backend": self.backend,
                   "supported_backends": self.available_backends(), "checks": {}}
        if not self._platform.startswith("linux"):
            return {**blocked, "reason": "Linux namespace isolation is required"}
        if self.backend not in SUPPORTED_BACKENDS:
            return {**blocked, "reason": "Unsupported backend; no unsafe fallback is available"}
        if shutil.which(self.apptainer_binary) is None:
            return {**blocked, "reason": "Apptainer executable is unavailable"}
        if not self.runtime_image.is_file() or not (self.runtime_env / "bin/python").is_file():
            return {**blocked, "reason": "Analysis SIF or Python runtime is unavailable"}
        try:
            _no_symlink_components(self.workdir)
            host_net = os.readlink("/proc/self/ns/net") if os.name == "posix" else "unit-test-host"
            with tempfile.TemporaryDirectory(prefix=".sandbox-probe-", dir=self.workdir) as folder:
                parent = Path(folder)
                work, inputs = parent / "work", parent / "inputs"
                work.mkdir(); inputs.mkdir()
                (inputs / "sentinel").write_text("primx-synthetic-input", encoding="utf-8")
                code = _probe_code(str(parent), host_net,
                                   self.memory_limit_bytes, self.file_size_limit_bytes)
                result = self._invoke(self._command(work, [inputs], ["-c", code]), 30)
            if result.get("timed_out") or result.get("exit_code") != 0:
                return {**blocked, "reason": "Isolation probe could not execute", "execution": result}
            lines = [line[len(PROBE_MARKER):] for line in result["stdout"].splitlines()
                     if line.startswith(PROBE_MARKER)]
            checks = json.loads(lines[-1]) if lines else {}
            required = ("python_ok", "input_readable", "input_write_blocked", "work_writable",
                        "tmp_write_blocked", "host_path_hidden", "network_isolated",
                        "environment_clean", "home_is_work", "host_gpu_hidden",
                        "address_space_limit_enforced", "file_size_limit_enforced",
                        "hard_limits_cannot_be_raised")
            if self.fs_license_file is not None:
                required += ("freesurfer_license_present", "freesurfer_license_readonly")
            if any(checks.get(key) is not True for key in required):
                return {**blocked, "reason": "Required isolation checks failed", "checks": checks,
                        "stderr": result["stderr"]}
            return {"status": "ready", "backend": self.backend, "checks": checks,
                    "input_mapping": [f"/inputs/{i}" for i in range(len(self.input_roots))],
                    "writable_host_mounts": ["/work"], "supported_backends": self.available_backends()}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return {**blocked, "reason": f"Isolation probe failed: {str(exc)[:1000]}"}

    def inspect_runtime(self) -> dict[str, Any]:
        """Inspect actual isolated software locations without mounting study inputs.

        Presence and version metadata do not certify that a command runs or that
        an algorithm applies. No study computation or model execution receipt is
        created, and no caller-supplied path or command is executed.
        """
        capability = self.probe()
        if capability["status"] != "ready":
            return {"status": "blocked", "reason": capability.get("reason"),
                    "isolation": capability}
        try:
            with tempfile.TemporaryDirectory(prefix=".runtime-inventory-", dir=self.workdir) as folder:
                work = Path(folder)
                result = self._invoke(self._command(work, [], ["-c", _runtime_inventory_code()]), 180)
            if result.get("timed_out") or result.get("exit_code") != 0:
                return {"status": "error", "reason": "Runtime inventory did not finish",
                        "execution": result}
            prefix = "PRIMATEX_RUNTIME_INVENTORY="
            lines = [line[len(prefix):] for line in result["stdout"].splitlines()
                     if line.startswith(prefix)]
            inventory = json.loads(lines[-1]) if lines else None
            if not isinstance(inventory, dict) or inventory.get("schema_version") != 1:
                return {"status": "error", "reason": "Invalid runtime inventory response"}
            return {"status": "ok", "inventory": inventory, "backend": self.backend,
                    "isolation_verified": True, "study_inputs_mounted_for_inventory": False,
                    "analysis_performed": False, "command_execution_verified": any(row.get("executed") for row in inventory.get("commands", {}).values()),
                    "input_mapping": capability.get("input_mapping", []),
                    "interpretation": "Fixed command help/version probes and package metadata; scientific input applicability is not verified."}
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return {"status": "error", "reason": str(exc)[:1000]}

    def run(self, script_path: Path, timeout_seconds: int = 120, *,
            frozen_source: Path | None = None, work_read_only: bool = False) -> dict[str, Any]:
        maximum = 86400 if frozen_source is not None else 3600
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= maximum:
            raise ValueError(f"timeout_seconds must be an integer between 1 and {maximum}")
        script = Path(script_path)
        script = _absolute_path(script if script.is_absolute() else self.workdir / script)
        if not script.is_relative_to(self.workdir) or script.suffix != ".py" or not script.is_file():
            raise ValueError("script_path must be a regular .py file inside workdir")
        capability = self.probe()
        if capability["status"] != "ready":
            return {"status": "blocked", "exit_code": None, "stdout": "", "stderr": capability.get("reason", "Isolation unavailable"),
                    "artifacts": [], "backend": self.backend, "probe": capability,
                    "stdout_truncated": False, "stderr_truncated": False}
        # Revalidate mount sources immediately before launch.
        _no_symlink_components(self.workdir)
        _no_symlink_components(script)
        for root in self.input_roots:
            _no_symlink_components(root)
            if not root.is_dir():
                raise ValueError("An input root is no longer an existing directory")
        target = "/work/" + script.relative_to(self.workdir).as_posix()
        result = self._invoke(self._command(self.workdir, self.input_roots, [target],
                                           frozen_source=frozen_source,
                                           frozen_target=target if frozen_source is not None else None,
                                           work_read_only=work_read_only), timeout_seconds)
        status = "timeout" if result.get("timed_out") else ("success" if result.get("exit_code") == 0 else "failed")
        return {"status": status, "exit_code": result.get("exit_code"), "stdout": result["stdout"],
                "stderr": result["stderr"], "stdout_truncated": result["stdout_truncated"],
                "stderr_truncated": result["stderr_truncated"], "backend": self.backend,
                "resource_limits": {
                    "address_space_bytes": capability["checks"].get("address_space_bytes"),
                    "max_file_size_bytes": capability["checks"].get("max_file_size_bytes"),
                    "scope": "per_process_address_space_and_per_file_not_aggregate_quota",
                },
                "artifacts": self._artifacts(script)}

    def _artifacts(self, script: Path) -> list[str]:
        found: list[str] = []
        seen = 0
        for base, dirs, files in os.walk(self.workdir, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (Path(base) / d).is_symlink())
            for name in sorted(files):
                seen += 1
                if seen > 2000 or len(found) >= 100:
                    return found
                path = Path(base) / name
                if path == script or name.startswith(".") or path.is_symlink() or not path.is_file():
                    continue
                found.append(path.relative_to(self.workdir).as_posix()[:1000])
        return found


def _probe_code(host_sentinel_parent: str, host_net: str,
                memory_limit: int, file_limit: int) -> str:
    return f'''import errno, json, os, resource, socket
from pathlib import Path
import numpy
checks = {{"python_ok": True, "numpy_version": numpy.__version__}}
checks["input_readable"] = Path("/inputs/0/sentinel").read_text() == "primx-synthetic-input"
def blocked_write(path):
    try:
        Path(path).write_text("synthetic probe")
        return False
    except OSError as exc:
        return exc.errno in (errno.EROFS, errno.EACCES, errno.EPERM)
checks["input_write_blocked"] = blocked_write("/inputs/0/write-probe")
checks["tmp_write_blocked"] = blocked_write("/tmp/primx-write-probe")
Path("/work/write-probe").write_text("synthetic probe")
checks["work_writable"] = True
checks["host_path_hidden"] = not Path({host_sentinel_parent!r}).exists()
checks["network_isolated"] = os.readlink("/proc/self/ns/net") != {host_net!r} and all(name == "lo" for _, name in socket.if_nameindex())
checks["environment_clean"] = set(os.environ) <= {{"HOME", "TMPDIR", "MPLCONFIGDIR", "LANG", "PATH", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "LC_CTYPE", "FS_LICENSE"}}
checks["home_is_work"] = os.environ.get("HOME") == "/work"
if "FS_LICENSE" in os.environ:
    license_path = Path(os.environ["FS_LICENSE"])
    checks["freesurfer_license_present"] = license_path.is_file()
    checks["freesurfer_license_readonly"] = bool(os.statvfs(license_path).f_flag & os.ST_RDONLY)
checks["host_gpu_hidden"] = not Path("/dev/nvidia0").exists()
address_soft, address_hard = resource.getrlimit(resource.RLIMIT_AS)
file_soft, file_hard = resource.getrlimit(resource.RLIMIT_FSIZE)
checks["address_space_bytes"] = address_hard
checks["max_file_size_bytes"] = file_hard
checks["address_space_limit_enforced"] = address_soft == address_hard and 0 < address_hard <= {memory_limit}
checks["file_size_limit_enforced"] = file_soft == file_hard and 0 < file_hard <= {file_limit}
def cannot_raise(kind):
    old = resource.getrlimit(kind)
    try:
        resource.setrlimit(kind, (old[1] + 4096, old[1] + 4096))
        resource.setrlimit(kind, old)
        return False
    except (OSError, ValueError):
        return True
checks["hard_limits_cannot_be_raised"] = cannot_raise(resource.RLIMIT_AS) and cannot_raise(resource.RLIMIT_FSIZE)
print({PROBE_MARKER!r} + json.dumps(checks))
'''


def _runtime_inventory_code() -> str:
    # Fixed metadata probes; never user arguments, provider credentials or data.
    if __package__:
        from .analysis_software import PROBE_SOURCE
    else:
        # Standalone executor security tests load this file without a package.
        import runpy
        PROBE_SOURCE = runpy.run_path(str(Path(__file__).with_name("analysis_software.py")))["PROBE_SOURCE"]
    return PROBE_SOURCE + r'''import sys, os, json, shutil, glob
from pathlib import Path
from importlib import metadata
packages = {}
for name in ("numpy", "scipy", "nibabel", "nilearn", "pandas", "matplotlib", "Pillow", "SimpleITK", "scikit-learn", "scikit-image"):
    try: packages[name] = {"installed": True, "version": metadata.version(name)}
    except metadata.PackageNotFoundError: packages[name] = {"installed": False}
commands = {}
names = ("fast", "bet", "fslstats", "fslmaths", "flirt", "fnirt", "randomise", "fslvbm_1_bet", "mri_surf2surf", "mris_preproc", "mris_anatomical_stats", "mri_segstats", "recon-all", "matlab", "mris_info", "mris_compute_lgi", "antsRegistration", "antsApplyTransforms", "wb_command", "mrconvert")
patterns = ("/opt/fsl*/share/fsl/bin/{name}", "/opt/fsl*/bin/{name}", "/opt/freesurfer*/bin/{name}", "/opt/ants*/bin/{name}", "/opt/ants*/{name}", "/opt/workbench/bin_linux64/{name}", "/opt/mrtrix*/bin/{name}")
for name in names:
    on_path = shutil.which(name)
    found = [on_path] if on_path else []
    for pattern in patterns:
        found.extend(sorted(glob.glob(pattern.format(name=name)))[:8])
    paths = sorted(set(p for p in found if p and Path(p).is_file() and os.access(p, os.X_OK)))[:12]
    row = probe_command(name)
    # Inventory is a compact discovery view. The prerequisite probe retains
    # its own longer command evidence. Keep this JSON below the transport cap.
    commands[name] = {key: row.get(key) for key in ("command", "executed", "exit_code", "executable", "accepted_nonzero_version_exit")}
    commands[name]["executable_locations"] = row.get("locations", [])[:3]
    commands[name]["default_path_resolution"] = row.get("default_path_resolution")
    commands[name]["argv"] = row.get("argv", [])
    commands[name]["stdout_excerpt"] = row.get("stdout", "")[:120]
    commands[name]["stderr_excerpt"] = row.get("stderr", "")[:120]
    commands[name]["excerpt_truncated"] = len(row.get("stdout", "")) > 120 or len(row.get("stderr", "")) > 120
    commands[name]["location_count"] = len(row.get("locations", []))
versions = []
for pattern in ("/opt/fsl*/etc/fslversion", "/opt/freesurfer*/build-stamp.txt"):
    for name in sorted(glob.glob(pattern))[:8]:
        try:
            with open(name, "r", encoding="utf-8", errors="replace") as f: value = f.read(512).strip()
            versions.append({"source": name, "value": value})
        except OSError: pass
roots = []
for pattern in ("/opt/fsl*", "/opt/freesurfer*", "/opt/ants*", "/opt/workbench", "/opt/mrtrix*"):
    roots.extend(p for p in sorted(glob.glob(pattern))[:8] if Path(p).is_dir())
value = {"schema_version": 1, "python": sys.version.split()[0], "python_executable": sys.executable,
         "default_path": os.environ.get("PATH", ""), "packages": packages,
         "commands": commands, "version_files": versions, "software_roots": sorted(set(roots)),
         "setup_references": [{"software": "FSL", "url": "https://fsl.fmrib.ox.ac.uk/fsl/docs/install/configuration.html", "note": "Use installed FSLDIR and verify its configuration. Prefer share/fsl/bin wrappers if present to avoid replacing the analysis Python; explicit binary paths are also inspectable. Do not assume PATH discovery proves absence."}, {"software": "FreeSurfer", "url": "https://surfer.nmr.mgh.harvard.edu/fswiki/SetupConfiguration_Linux", "note": "Inspect installed FREESURFER_HOME, SUBJECTS_DIR, command help and license availability before execution."}],
         "limitations": ["File presence is not successful command execution", "No algorithms or study data inspected", "This bounded catalogue is not exhaustive; missing entries are not proof software is absent", "Installed version metadata is not a scientific applicability check"]}
print("PRIMATEX_RUNTIME_INVENTORY=" + json.dumps(value, separators=(",", ":")))
'''
