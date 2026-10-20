"""Output contracts are structural; independent references are server configured."""

import json
import importlib.util
import os
import time
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "analysis_validation_under_test", Path(__file__).resolve().parents[1] / "backend" / "analysis_validation.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

ArtifactValidator = module.ArtifactValidator


def png_bytes():
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


class ArtifactValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.work = self.base / "work"
        self.work.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, artifacts, **extra):
        data = {"schema_version": module.MANIFEST_VERSION, "artifacts": artifacts, **extra}
        (self.work / module.MANIFEST_NAME).write_text(json.dumps(data), encoding="utf-8")

    def csv(self, content="region,mean,count\nA,1.25,3\nB,2.5,4\n", **rules):
        (self.work / "stats.csv").write_text(content, encoding="utf-8")
        spec = {
            "path": "stats.csv", "kind": "csv", "columns": ["region", "mean", "count"],
            "row_count": 2, "finite_columns": ["mean", "count"],
            "unique_columns": ["region"], **rules,
        }
        self.manifest([spec])
        return spec

    def reference(self, content="region,mean,count\nA,1.25,3\nB,2.5,4\n", **rules):
        folder = self.base / "trusted"
        folder.mkdir(exist_ok=True)
        (folder / "gold.csv").write_text(content, encoding="utf-8")
        path = folder / "reference.json"
        config = {
            "schema_version": module.REFERENCE_VERSION,
            "tables": [{
                "artifact_path": "stats.csv", "reference_path": "gold.csv",
                "key_columns": ["region"], "value_columns": ["mean"],
                "exact_columns": ["count"], "rtol": 1e-7, "atol": 1e-9, **rules,
            }],
        }
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def test_good_csv_json_png_contract_without_scientific_claim(self):
        spec = self.csv(shape=[2, 3], exact_columns=True, numeric_ranges={"mean": {"min": 0, "max": 5}})
        (self.work / "summary.json").write_text(
            json.dumps({"methods": "descriptive", "limitations": ["single case"], "matrix": [[1, 2], [3, 4]]}),
            encoding="utf-8",
        )
        (self.work / "plot.png").write_bytes(png_bytes())
        self.manifest([
            spec,
            {"path": "summary.json", "kind": "json", "required_keys": ["methods", "limitations"], "data_key": "matrix", "shape": [2, 2]},
            {"path": "plot.png", "kind": "png", "shape": [1, 1]},
        ])
        result = ArtifactValidator().validate(self.work)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["passed"], result["valid"])
        self.assertEqual(len(result["artifacts"]), 3)
        self.assertEqual(result["scientific_status"], "not_evaluated")
        self.assertEqual(result["independent_numeric_status"], "not_configured")
        self.assertEqual(result["artifacts"][2]["visual_quality"], "not_evaluated")

    def test_missing_manifest_and_no_artifacts_fail(self):
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])
        self.manifest([])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_missing_output_and_empty_output_fail(self):
        self.manifest([{"path": "missing.csv", "kind": "csv"}])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])
        (self.work / "missing.csv").write_bytes(b"")
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_nonfinite_numeric_and_non_numeric_declared_column_fail(self):
        for bad in ("NaN", "inf", "-Inf", "1e999", "not a number", ""):
            with self.subTest(bad=bad):
                self.csv(f"region,mean,count\nA,{bad},3\nB,2.5,4\n")
                self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_numeric_nonfinite_is_rejected_even_without_finite_columns(self):
        self.csv("region,mean,count\nA,NaN,3\nB,2.5,4\n", finite_columns=[])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_row_column_shape_and_unique_checks_detect_errors(self):
        variants = [
            {"row_count": 3},
            {"columns": ["missing"]},
            {"shape": [2, 4]},
            {"unique_columns": ["count"]},
            {"numeric_ranges": {"mean": {"max": 2}}},
        ]
        for rules in variants:
            with self.subTest(rules=rules):
                self.csv("region,mean,count\nA,1.25,3\nB,2.5,3\n", **rules)
                self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_duplicate_header_ragged_rows_and_duplicate_keys_fail(self):
        for content in (
            "region,mean,mean\nA,1,2\nB,2,3\n",
            "region,mean,count\nA,1\nB,2,3\n",
            "region,mean,count\nA,1,2\nA,2,3\n",
        ):
            with self.subTest(content=content):
                self.csv(content)
                self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_declared_zero_row_table_is_allowed(self):
        self.csv("region,mean,count\n", row_count=0)
        self.assertTrue(ArtifactValidator().validate(self.work)["valid"])

    def test_paths_cannot_escape_workdir(self):
        (self.base / "outside.csv").write_text("a\n1\n", encoding="utf-8")
        for path in ("../outside.csv", "/etc/passwd", r"C:\outside.csv", "x/../../outside.csv", "x//y.csv"):
            with self.subTest(path=path):
                self.manifest([{"path": path, "kind": "csv"}])
                self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_symlink_artifact_cannot_escape_workdir(self):
        outside = self.base / "outside.csv"
        outside.write_text("a\n1\n", encoding="utf-8")
        try:
            (self.work / "link.csv").symlink_to(outside)
        except OSError:
            self.skipTest("Symlink creation not available")
        self.manifest([{"path": "link.csv", "kind": "csv"}])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_duplicate_declarations_and_manifest_as_artifact_fail(self):
        spec = self.csv()
        self.manifest([spec, spec])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])
        self.manifest([{"path": module.MANIFEST_NAME, "kind": "json"}])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_false_scientific_validation_claims_are_rejected(self):
        self.csv()
        self.manifest([{"path": "stats.csv", "kind": "csv"}], scientific_validated=True)
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])
        (self.work / "summary.json").write_text('{"nested":{"scientific_validated":true}}', encoding="utf-8")
        self.manifest([{"path": "summary.json", "kind": "json"}])
        result = ArtifactValidator().validate(self.work)
        self.assertFalse(result["valid"])
        self.assertEqual(result["scientific_status"], "not_evaluated")

    def test_json_duplicate_keys_nonfinite_and_ragged_shape_fail(self):
        for content in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}', '[[1],[2,3]]'):
            with self.subTest(content=content):
                (self.work / "data.json").write_text(content, encoding="utf-8")
                spec = {"path": "data.json", "kind": "json"}
                if content.startswith("["):
                    spec["shape"] = [2, 1]
                self.manifest([spec])
                self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_json_missing_keys_and_deep_shape_fail_boundedly(self):
        (self.work / "data.json").write_text('{"a":1}', encoding="utf-8")
        self.manifest([{"path": "data.json", "kind": "json", "required_keys": ["b"]}])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])
        data = 1
        for _ in range(20):
            data = [data]
        (self.work / "data.json").write_text(json.dumps(data), encoding="utf-8")
        self.manifest([{"path": "data.json", "kind": "json", "shape": [1] * 20}])
        self.assertTrue(ArtifactValidator().validate(self.work)["valid"])

    def test_json_finite_rule_checks_numeric_type_not_only_json_parse(self):
        (self.work / "data.json").write_text('{"matrix":[1,"NaN"]}', encoding="utf-8")
        self.manifest([{"path": "data.json", "kind": "json", "data_key": "matrix", "finite": True}])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_png_signature_alone_and_bad_stream_fail(self):
        for content in (b"\x89PNG\r\n\x1a\nfixture", png_bytes()[:-1]):
            (self.work / "plot.png").write_bytes(content)
            self.manifest([{"path": "plot.png", "kind": "png"}])
            self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_read_limit_and_unsupported_rules_fail(self):
        self.csv()
        with patch.object(module, "MAX_ARTIFACT_BYTES", 10):
            self.assertFalse(ArtifactValidator().validate(self.work)["valid"])
        self.csv(unrecognized_check="pretend_valid")
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])

    def test_model_cannot_nominate_an_independent_reference(self):
        spec = self.csv()
        self.manifest([spec], reference_manifest="../trusted/reference.json")
        result = ArtifactValidator().validate(self.work)
        self.assertFalse(result["valid"])
        self.assertEqual(result["independent_numeric_status"], "not_configured")

    def test_server_reference_pass_is_numerical_only_and_key_order_independent(self):
        self.csv("region,mean,count\nB,2.5,4\nA,1.25,3\n")
        result = ArtifactValidator(self.reference()).validate(self.work)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["independent_numeric_status"], "passed")
        self.assertEqual(result["scientific_status"], "not_evaluated")
        self.assertIn("server_reference_table", [item["check"] for item in result["checks"]])

    def test_reference_wrong_value_keys_and_exact_fields_are_rejected(self):
        for content in (
            "region,mean,count\nA,9,3\nB,2.5,4\n",
            "region,mean,count\nC,1.25,3\nB,2.5,4\n",
            "region,mean,count\nA,1.25,7\nB,2.5,4\n",
        ):
            with self.subTest(content=content):
                self.csv(content)
                result = ArtifactValidator(self.reference()).validate(self.work)
                self.assertFalse(result["valid"])
                self.assertEqual(result["independent_numeric_status"], "failed")

    def test_reference_values_are_not_returned_in_feedback(self):
        self.csv()
        result = ArtifactValidator(self.reference("region,mean,count\nA,123.456789,3\nB,2.5,4\n")).validate(self.work)
        self.assertFalse(result["valid"])
        self.assertNotIn("123.456789", json.dumps(result))

    def test_reference_must_be_server_owned_outside_workdir(self):
        self.csv()
        path = self.work / "oracle.json"
        path.write_text(json.dumps({"schema_version": module.REFERENCE_VERSION, "tables": []}), encoding="utf-8")
        result = ArtifactValidator(path).validate(self.work)
        self.assertFalse(result["valid"])
        self.assertEqual(result["independent_numeric_status"], "failed")

    def test_trusted_reference_path_is_still_bounded(self):
        self.csv()
        path = self.reference(reference_path="../work/stats.csv")
        self.assertFalse(ArtifactValidator(path).validate(self.work)["valid"])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO test requires POSIX")
    def test_fifo_manifest_artifact_and_reference_fail_without_blocking(self):
        started = time.monotonic()
        manifest_path = self.work / module.MANIFEST_NAME
        os.mkfifo(manifest_path)
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])
        manifest_path.unlink()
        os.mkfifo(self.work / "pipe.csv")
        self.manifest([{"path": "pipe.csv", "kind": "csv"}])
        self.assertFalse(ArtifactValidator().validate(self.work)["valid"])
        self.csv()
        reference_path = self.base / "reference.json"
        os.mkfifo(reference_path)
        self.assertFalse(ArtifactValidator(reference_path).validate(self.work)["valid"])
        # Exercise the low-level reader too: an object can change after the
        # earlier path check, so the open must remain nonblocking.
        with self.assertRaises(ValueError):
            module._read_bytes(self.work / "pipe.csv", 1024, self.work)
        self.assertLess(time.monotonic() - started, 2)


if __name__ == "__main__":
    unittest.main()

