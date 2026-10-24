"""Unit coverage plus opt-in real Linux namespace/analysis-runtime checks."""
import json
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# The existing backend package imports FastAPI eagerly; this standalone security
# unit must remain testable without the unrelated web/model dependencies.
_spec = importlib.util.spec_from_file_location(
    "analysis_executor_under_test",
    Path(__file__).resolve().parents[1] / "backend" / "analysis_executor.py",
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
PROBE_MARKER = _module.PROBE_MARKER
SandboxExecutor = _module.SandboxExecutor
_run_bounded = _module._run_bounded


GOOD_CHECKS = {key: True for key in (
    "python_ok", "input_readable", "input_write_blocked", "work_writable",
    "tmp_write_blocked", "host_path_hidden", "network_isolated",
    "environment_clean", "home_is_work", "host_gpu_hidden",
    "address_space_limit_enforced", "file_size_limit_enforced", "hard_limits_cannot_be_raised",
)}


class ExecutorUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.work = self.base / "work"
        self.inputs = self.base / "inputs"
        self.inputs.mkdir()
        self.runtime = self.base / "runtime"
        (self.runtime / "bin").mkdir(parents=True)
        (self.runtime / "bin/python").write_text("test fixture")
        self.image = self.base / "fixture.sif"
        self.image.write_text("test fixture")
        self.commands = []

    def runner(self, command, **kwargs):
        self.commands.append((command, kwargs))
        if any(PROBE_MARKER in argument for argument in command):
            return {"exit_code": 0, "stdout": PROBE_MARKER + json.dumps(GOOD_CHECKS), "stderr": ""}
        return {"exit_code": 0, "stdout": "completed", "stderr": ""}

    def executor(self, runner=None, **kwargs):
        return SandboxExecutor(self.work, [self.inputs], runtime_image=self.image,
                               runtime_env=self.runtime, apptainer_binary=sys.executable,
                               platform_name="linux", command_runner=runner or self.runner, **kwargs)

    def script(self, name="analysis.py"):
        self.work.mkdir(exist_ok=True)
        path = self.work / name
        path.write_text("print('synthetic')")
        return path

    def test_command_enforces_readonly_inputs_network_and_clean_environment(self):
        executor = self.executor()
        result = executor.run(self.script())
        self.assertEqual(result["status"], "success")
        command, options = self.commands[-1]
        self.assertIn("--containall", command)
        self.assertIn("--net", command)
        self.assertIn("none", command)
        self.assertIn("bind-paths,hostfs,cwd,tmp", command)
        self.assertIn(f"{self.inputs}:/inputs/0:ro", command)
        self.assertIn(f"{self.runtime}:/opt/analysis:ro", command)
        self.assertIn(f"{self.work}:/work:rw", command)
        self.assertNotIn("/data:/data", command)
        self.assertIn("-i", command)
        self.assertIn("-I", command)
        self.assertEqual(set(options["env"]), {"PATH", "LANG", "HOME"})

    def test_failed_isolation_probe_blocks_script_execution(self):
        def fail(command, **kwargs):
            self.commands.append(command)
            return {"exit_code": 1, "stdout": "", "stderr": "network namespace denied"}
        result = self.executor(fail).run(self.script())
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(self.commands), 1)
        self.assertIn("network namespace denied", result["probe"]["execution"]["stderr"])

    def test_false_or_missing_probe_check_is_fail_closed(self):
        for checks in ({}, {**GOOD_CHECKS, "network_isolated": False}):
            with self.subTest(checks=checks):
                def runner(command, **kwargs):
                    return {"exit_code": 0, "stdout": PROBE_MARKER + json.dumps(checks), "stderr": ""}
                self.assertEqual(self.executor(runner).probe()["status"], "blocked")

    def test_escape_and_non_python_files_are_rejected_before_probe(self):
        executor = self.executor()
        outside = self.base / "outside.py"
        outside.write_text("pass")
        for path in (outside, Path("../outside.py"), self.script("analysis.txt")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                executor.run(path)
        self.assertEqual(self.commands, [])

    def test_symlink_script_and_input_are_rejected(self):
        self.script()
        link = self.work / "link.py"
        try:
            link.symlink_to(self.work / "analysis.py")
        except OSError:
            self.skipTest("Creating symlinks is not permitted on this host")
        with self.assertRaises(ValueError):
            self.executor().run(link)
        input_link = self.base / "input_link"
        input_link.symlink_to(self.inputs, target_is_directory=True)
        with self.assertRaises(ValueError):
            SandboxExecutor(self.work, [input_link])

    def test_overlapping_input_roots_are_rejected(self):
        with self.assertRaises(ValueError):
            SandboxExecutor(self.base / "nested", [self.base])

    def test_bounded_output_and_timeout_status(self):
        def runner(command, **kwargs):
            if any(PROBE_MARKER in argument for argument in command):
                return self.runner(command, **kwargs)
            return {"exit_code": -9, "stdout": "x" * 10000, "stderr": "e" * 10000, "timed_out": True}
        result = self.executor(runner, output_limit_bytes=1024).run(self.script())
        self.assertEqual(result["status"], "timeout")
        self.assertTrue(result["stdout_truncated"])
        self.assertLessEqual(len(result["stdout"].encode()), 1024)
        self.assertLessEqual(len(result["stderr"].encode()), 1024)

    def test_limits_are_server_configured_and_applied_by_trusted_launcher(self):
        with patch.dict(os.environ, {"AGENT_ANALYSIS_MEMORY_BYTES": "536870912",
                                     "AGENT_ANALYSIS_FILE_BYTES": "4096"}):
            executor = self.executor()
        executor.run(self.script())
        command = self.commands[-1][0]
        self.assertIn("536870912", command)
        self.assertIn("4096", command)
        launcher = command[command.index("-c") + 1]
        self.assertIn("resource.setrlimit", launcher)
        self.assertIn("RLIMIT_AS", launcher)
        self.assertIn("RLIMIT_FSIZE", launcher)
        self.assertNotIn("RLIMIT_NPROC", launcher)
        self.assertLess(command.index("4096"), command.index("/work/analysis.py"))

    def test_invalid_server_resource_limits_are_rejected(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.executor(memory_limit_bytes=value)

    def test_artifact_listing_does_not_follow_symlinks(self):
        executor = self.executor()
        script = self.script()
        (self.work / "result.csv").write_text("synthetic")
        (self.work / ".hidden").write_text("excluded")
        try:
            (self.work / "outside").symlink_to(self.inputs, target_is_directory=True)
        except OSError:
            pass
        self.assertEqual(executor.run(script)["artifacts"], ["result.csv"])

    def test_non_linux_and_unsupported_backend_fail_closed(self):
        executor = self.executor()
        executor._platform = "win32"
        self.assertEqual(executor.probe()["status"], "blocked")
        executor._platform = "linux"
        executor.backend = "unsafe"
        self.assertEqual(executor.probe()["status"], "blocked")


    def test_container_executable_defaults_to_apptainer(self):
        with patch.dict(os.environ, {}, clear=True):
            executor = SandboxExecutor(self.work, [self.inputs], runtime_image=self.image,
                                       runtime_env=self.runtime)
        self.assertEqual(executor.apptainer_binary, "apptainer")

    def test_host_container_settings_preserve_isolation_and_minimal_environment(self):
        settings = {"ANALYSIS_CONTAINER_CMD": "singularity",
                    "ANALYSIS_RUNTIME_IMAGE": str(self.image),
                    "ANALYSIS_RUNTIME_ENV": str(self.runtime)}
        with patch.dict(os.environ, settings):
            executor = SandboxExecutor(self.work, [self.inputs])
        with patch.object(_module.shutil, "which", return_value="/usr/local/bin/singularity"):
            command = executor._command(self.work, [self.inputs], ["-c", "pass"])
        self.assertEqual(command[0], "/usr/local/bin/singularity")
        for flag in ("--cleanenv", "--containall", "--no-home", "--net"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--network") + 1], "none")
        self.assertEqual(command[command.index("--no-mount") + 1], "bind-paths,hostfs,cwd,tmp")
        self.assertIn(f"{self.inputs}:/inputs/0:ro", command)
        self.assertIn(f"{self.runtime}:/opt/analysis:ro", command)
        self.assertIn(f"{self.work}:/work:rw", command)
        self.assertEqual(set(executor._environment()), {"PATH", "LANG", "HOME"})

    def test_explicit_container_arguments_override_host_environment(self):
        with patch.dict(os.environ, {"ANALYSIS_CONTAINER_CMD": "missing-container",
                                     "ANALYSIS_RUNTIME_IMAGE": "/not-the-image",
                                     "ANALYSIS_RUNTIME_ENV": "/not-the-runtime"}):
            executor = self.executor()
        self.assertEqual(executor.apptainer_binary, sys.executable)
        self.assertEqual(executor.runtime_image, self.image.resolve())
        self.assertEqual(executor.runtime_env, self.runtime.resolve())

    def test_empty_or_multiline_container_command_is_rejected(self):
        for value in ("", " ", "singularity\nexec"):
            with self.subTest(value=value), patch.dict(os.environ, {"ANALYSIS_CONTAINER_CMD": value}):
                with self.assertRaises(ValueError):
                    SandboxExecutor(self.work, [self.inputs], runtime_image=self.image,
                                    runtime_env=self.runtime)

    def test_empty_runtime_environment_setting_is_rejected(self):
        for variable in ("ANALYSIS_RUNTIME_IMAGE", "ANALYSIS_RUNTIME_ENV"):
            with self.subTest(variable=variable), patch.dict(os.environ, {variable: ""}):
                with self.assertRaises(ValueError):
                    SandboxExecutor(self.work, [self.inputs])


class BoundedProcessTests(unittest.TestCase):
    def test_output_is_drained_without_unbounded_retention(self):
        result = _run_bounded([sys.executable, "-c", "import sys;sys.stdout.write('x'*200000);sys.stderr.write('e'*200000)"],
                              timeout_seconds=10, env=os.environ.copy(), output_limit_bytes=1024)
        self.assertEqual(result["exit_code"], 0)
        self.assertTrue(result["stdout_truncated"])
        self.assertTrue(result["stderr_truncated"])
        self.assertEqual(len(result["stdout"]), 1024)

    @unittest.skipUnless(os.name == "posix", "Production executor requires Linux process groups")
    def test_timeout_terminates_a_descendant_process(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "descendant-survived"
            child_code = f"import time;from pathlib import Path;time.sleep(2);Path({str(marker)!r}).write_text('unsafe')"
            parent_code = ("import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"
                           + repr(child_code) + "]);time.sleep(60)")
            result = _run_bounded([sys.executable, "-c", parent_code], timeout_seconds=1,
                                  env=os.environ.copy(), output_limit_bytes=1024)
            self.assertTrue(result["timed_out"])
            time.sleep(2)
            self.assertFalse(marker.exists(), "Timed-out execution left a live descendant")


@unittest.skipUnless(os.environ.get("PRIMATEX_SANDBOX_INTEGRATION") == "1" and sys.platform.startswith("linux"),
                     "Set PRIMATEX_SANDBOX_INTEGRATION=1 on the configured Linux server")
class RealLinuxSandboxTests(unittest.TestCase):
    def test_real_analysis_runtime_and_namespace_boundary(self):
        with tempfile.TemporaryDirectory(prefix="primx-executor-test-") as folder:
            root = Path(folder)
            inputs = root / "input"; inputs.mkdir()
            (inputs / "value.txt").write_text("synthetic")
            executor = SandboxExecutor(root / "work", [inputs])
            self.assertEqual(executor.probe()["status"], "ready")
            script = executor.workdir / "analysis.py"
            script.write_text("from pathlib import Path\nimport numpy as np\n"
                              "import scipy.stats as stats\nimport nibabel as nib\nfrom nilearn.image import math_img\n"
                              "assert Path('/inputs/0/value.txt').read_text() == 'synthetic'\n"
                              "assert not Path('/data/xuancheng').exists()\n"
                              "sample=np.array([1.,2.,3.,4.,5.])\n"
                              "assert np.isfinite(stats.ttest_1samp(sample, 0).pvalue)\n"
                              "image=nib.Nifti1Image(np.ones((3,3,3)), np.eye(4))\n"
                              "assert np.allclose(math_img('img * 2', img=image).get_fdata(), 2)\n"
                              "Path('/work/result.txt').write_text(str(np.arange(5).sum()))\nprint('synthetic complete')\n")
            result = executor.run(script, timeout_seconds=30)
            self.assertEqual(result["status"], "success", result)
            self.assertIn("result.txt", result["artifacts"])
            self.assertEqual((executor.workdir / "result.txt").read_text(), "10")

    def test_real_timeout(self):
        with tempfile.TemporaryDirectory(prefix="primx-executor-timeout-") as folder:
            executor = SandboxExecutor(Path(folder) / "work", [])
            script = executor.workdir / "analysis.py"
            script.write_text("import time\ntime.sleep(60)\n")
            result = executor.run(script, timeout_seconds=3)
            self.assertEqual(result["status"], "timeout", result)

    def test_real_address_space_limit_rejects_oversized_mapping(self):
        with tempfile.TemporaryDirectory(prefix="primx-executor-memory-") as folder:
            executor = SandboxExecutor(Path(folder) / "work", [], memory_limit_bytes=512 * 1024 ** 2)
            script = executor.workdir / "analysis.py"
            script.write_text("import mmap, resource\n"
                              "limit=resource.getrlimit(resource.RLIMIT_AS)[1]\n"
                              "assert limit == 512 * 1024 ** 2\n"
                              "mmap.mmap(-1, limit * 2)\n")
            result = executor.run(script, timeout_seconds=30)
            self.assertEqual(result["status"], "failed", result)
            self.assertIn("Cannot allocate memory", result["stderr"])

    def test_real_file_size_limit_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory(prefix="primx-executor-filelimit-") as folder:
            executor = SandboxExecutor(Path(folder) / "work", [], file_size_limit_bytes=4096)
            script = executor.workdir / "analysis.py"
            script.write_text("import resource\n"
                              "assert resource.getrlimit(resource.RLIMIT_FSIZE) == (4096,4096)\n"
                              "with open('/work/oversized.bin','wb') as handle: handle.write(b'x' * 65536)\n")
            result = executor.run(script, timeout_seconds=30)
            self.assertEqual(result["status"], "failed", result)
            self.assertLessEqual((executor.workdir / "oversized.bin").stat().st_size, 4096)


if __name__ == "__main__":
    unittest.main()
