import hashlib
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from report import (EvidenceError, Snapshot, build_report, main, markdown, observable_record,
                    residual_result, safe_path, strict_json)
import numpy as np

STAGE = Path(__file__).resolve().parents[1] / "reference_correction"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PureChecks(unittest.TestCase):
    def test_nonfinite_and_duplicate_json(self):
        for payload in ['{"value":NaN}', '{"value":Infinity}', '{"value":1e9999}', '{"x":1,"x":2}']:
            with self.subTest(payload=payload), self.assertRaises(EvidenceError):
                strict_json(payload)

    def test_path_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "valid").write_text("ok")
            (root / "link").symlink_to(root / "valid")
            for path in ['../valid', '/etc/passwd', './valid', 'link', 'missing', 'x\\y']:
                with self.subTest(path=path), self.assertRaises(EvidenceError):
                    safe_path(root, path)
            self.assertEqual(safe_path(root, "valid"), root / "valid")

    def test_residual_rules(self):
        self.assertFalse(residual_result(np.zeros((48, 3)))["alarm"])
        self.assertTrue(residual_result(np.zeros((48, 3)), False)["alarm"])
        self.assertTrue(residual_result(np.full((48, 3), .3))["alarm"])
        with self.assertRaises(EvidenceError):
            residual_result(np.zeros((3, 48)))
        with self.assertRaises(EvidenceError):
            residual_result(np.full((48, 3), np.nan))
        with self.assertRaises(EvidenceError):
            residual_result(np.zeros((48, 3)), "true")

    def test_observable_review_never_releases(self):
        for success in [False, True]:
            for branch in ["raw", "corrected"]:
                residual = residual_result(np.zeros((48, 3)), success)
                record = observable_record("case", branch, success, residual, residual,
                                           {"samples": 10, "offset_K": [0, 0, 0], "mean_standard_error_K": [0, 0, 0]})
                self.assertEqual(record["engineering_release"], "not_supported")
                self.assertIn("missing_reference_and_applicability_evidence", record["review_reasons"])
                self.assertFalse({"scenario", "score", "truth", "inadequate_prediction"}.intersection(record))

    def test_duplicate_manifest_and_wrong_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "results").mkdir()
            (root / "data").write_text("ok")
            entries = [{"file": "data", "sha256": digest(root / "data")}] * 2
            manifest = root / "results/artifact-manifest.json"
            manifest.write_text(json.dumps(entries))
            with self.assertRaisesRegex(EvidenceError, "Duplicate"):
                Snapshot(root, digest(manifest))
            with self.assertRaisesRegex(EvidenceError, "Manifest SHA"):
                Snapshot(root, "0" * 64)


class RealStudyChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = digest(STAGE / "results/artifact-manifest.json")
        cls.report = build_report(STAGE, cls.pin)

    def test_real_counts_and_missing_evidence(self):
        self.assertEqual(self.report["counts"], {"branches": 32, "alarmed": 8, "retrospective_inadequate": 14, "retrospective_missed": 6})
        self.assertEqual(len(self.report["missing_evidence"]), 5)
        self.assertEqual(self.report["engineering_release"], "not_supported")
        bad_reference = [case for case in self.report["retrospective_evaluation"]["cases"]
                         if case["scenario"] == "reference_bias" and case["branch"] == "corrected"]
        self.assertEqual(sum(case["missed_by_residual_rule"] for case in bad_reference), 4)

    def test_truth_does_not_enter_observable_reasons(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = self.copy_stage(Path(temporary))
            location = "results/object-0/noise-0-reference_bias/corrected"
            with np.load(stage / "results/object-0/truth.npz") as data:
                truth, times = data["temperature"], data["time"]
            np.savez_compressed(stage / location / "prediction.npz", temperature=truth, time=times)
            case_path = stage / location / "case.json"
            case = json.loads(case_path.read_text())
            case["score"] = {"rmse_K": 0.0, "final_mean_error_K": 0.0, "inadequate": False}
            case_path.write_text(json.dumps(case))
            manifest = stage / "results/artifact-manifest.json"
            entries = json.loads(manifest.read_text())
            for entry in entries:
                if entry["file"] in [f"{location}/prediction.npz", f"{location}/case.json"]:
                    entry["sha256"] = digest(stage / entry["file"])
            manifest.write_text(json.dumps(entries))
            changed = build_report(stage, digest(manifest))
            self.assertEqual(changed["observable_review"], self.report["observable_review"])
            self.assertEqual(changed["counts"]["retrospective_inadequate"], self.report["counts"]["retrospective_inadequate"] - 1)
            self.assertEqual(changed["engineering_release"], "not_supported")
        text = markdown(self.report)
        self.assertIn("仅仿真端可知", text)
        self.assertIn("不支持工程放行", text)

    def copy_stage(self, root):
        stage = root / "reference_correction"
        shutil.copytree(STAGE, stage, ignore=shutil.ignore_patterns('__pycache__'))
        config = json.loads((stage / "results/config.json").read_text())
        for relative in config["hashes"]:
            if "/" in relative:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(STAGE.parent / relative, destination)
        return stage

    def test_corrupted_evidence_fails_without_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = self.copy_stage(Path(temporary))
            target = stage / "results/object-0/noise-0-clean/raw/fit.json"
            target.write_text(target.read_text() + " ")
            output, error = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                result = main(["--stage", str(stage), "--manifest-sha256", self.pin])
            self.assertEqual(result, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("SHA-256 mismatch", error.getvalue())

    def test_rehashed_but_inconsistent_hidden_label_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = self.copy_stage(Path(temporary))
            relative = "results/object-0/noise-0-reference_bias/corrected/case.json"
            target = stage / relative
            case = json.loads(target.read_text())
            case["score"]["inadequate"] = False
            target.write_text(json.dumps(case))
            manifest = stage / "results/artifact-manifest.json"
            entries = json.loads(manifest.read_text())
            for entry in entries:
                if entry["file"] == relative:
                    entry["sha256"] = digest(target)
            manifest.write_text(json.dumps(entries))
            with self.assertRaisesRegex(EvidenceError, "hidden prediction label"):
                build_report(stage, digest(manifest))

    def test_missing_recorded_file_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = self.copy_stage(Path(temporary))
            (stage / "results/object-0/noise-0-clean/raw/prediction.npz").unlink()
            with self.assertRaisesRegex(EvidenceError, "Missing evidence"):
                build_report(stage, self.pin)

    def test_unlisted_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = self.copy_stage(Path(temporary))
            manifest = stage / "results/artifact-manifest.json"
            entries = json.loads(manifest.read_text())
            removed = "results/object-0/noise-0-clean/raw/residuals.npz"
            manifest.write_text(json.dumps([entry for entry in entries if entry["file"] != removed]))
            with self.assertRaisesRegex(EvidenceError, "not in manifest"):
                build_report(stage, digest(manifest))

    def test_cli_success_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["--stage", str(STAGE), "--manifest-sha256", self.pin])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), self.report)

    def test_nonfinite_saved_residual_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = self.copy_stage(Path(temporary))
            relative = "results/object-0/noise-0-clean/raw/residuals.npz"
            with np.load(stage / relative) as original:
                training, diagnostic = original["training"].copy(), original["diagnostic"].copy()
            training[0, 0] = np.nan
            np.savez_compressed(stage / relative, training=training, diagnostic=diagnostic)
            manifest = stage / "results/artifact-manifest.json"
            entries = json.loads(manifest.read_text())
            for entry in entries:
                if entry["file"] == relative:
                    entry["sha256"] = digest(stage / relative)
            manifest.write_text(json.dumps(entries))
            with self.assertRaisesRegex(EvidenceError, "Invalid numeric array"):
                build_report(stage, digest(manifest))

    def test_source_dependency_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.copy_stage(root)
            with (root / "radiation/model.py").open("a") as source:
                source.write("\n")
            with self.assertRaisesRegex(EvidenceError, "Dependency changed"):
                build_report(stage, self.pin)


if __name__ == "__main__":
    unittest.main(verbosity=2)
