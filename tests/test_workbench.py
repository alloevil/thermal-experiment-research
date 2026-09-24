import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import workbench


def fixture(root, entries=None):
    folder = root / "demo"
    (folder / "results").mkdir(parents=True)
    (folder / "payload.txt").write_text("immutable evidence\n")
    if entries is None:
        entries = [{"file": "payload.txt", "sha256": workbench.sha256(folder / "payload.txt")}]
    manifest = folder / "results/artifact-manifest.json"
    manifest.write_text(json.dumps(entries))
    return ("demo", "fixture", workbench.sha256(manifest), len(entries))


class SnapshotTests(unittest.TestCase):
    def test_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = fixture(root)
            result = workbench.check_snapshots(root, [stage])
            self.assertEqual(result["status"], "matched_snapshot")
            self.assertEqual(result["verified_artifacts"], 1)
            self.assertEqual(result["engineering_release"], "not_supported")

    def test_tamper_and_missing_artifact(self):
        for mode in ["tamper", "delete"]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                stage = fixture(root)
                target = root / "demo/payload.txt"
                if mode == "tamper":
                    target.write_text("changed")
                else:
                    target.unlink()
                result = workbench.check_stage(root, stage)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["verified_artifacts"], 0)
                self.assertTrue(result["errors"])

    def test_rewritten_manifest_requires_new_pin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = fixture(root)
            target = root / "demo/payload.txt"
            target.write_text("changed")
            (root / "demo/results/artifact-manifest.json").write_text(json.dumps([
                {"file": "payload.txt", "sha256": workbench.sha256(target)}]))
            result = workbench.check_stage(root, stage)
            self.assertEqual(result["status"], "invalid")
            self.assertIn("pin", result["errors"][0])

    def test_duplicate_invalid_keys_and_numbers(self):
        payloads = ['[]', '{}', '[{"file":"x","file":"y","sha256":"' + '0' * 64 + '"}]',
                    '[{"file":"x","sha256":NaN}]', '[{"file":"x","sha256":1e999}]',
                    '[{"file":"x","sha256":"bad"}]', '[{"file":[],"sha256":"' + '0' * 64 + '"}]']
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(workbench.SnapshotError):
                workbench.parse_manifest(payload)
        entry = {"file": "x", "sha256": "0" * 64}
        with self.assertRaises(workbench.SnapshotError):
            workbench.parse_manifest(json.dumps([entry, entry]))

    def test_unsafe_manifest_paths(self):
        for name in ["../outside", "/etc/passwd", "./payload.txt", "a/../payload.txt", "a\\payload.txt"]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                stage = fixture(root, [{"file": name, "sha256": "0" * 64}])
                self.assertEqual(workbench.check_stage(root, stage)["status"], "invalid")

    def test_file_and_stage_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = fixture(root)
            target = root / "demo/payload.txt"
            moved = root / "outside"
            target.rename(moved)
            target.symlink_to(moved)
            self.assertEqual(workbench.check_stage(root, stage)["status"], "invalid")
            target.unlink()
            moved.rename(target)
            (root / "demo").rename(root / "real-demo")
            (root / "demo").symlink_to(root / "real-demo", target_is_directory=True)
            self.assertEqual(workbench.check_stage(root, stage)["status"], "invalid")

    def test_count_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = fixture(root)
            changed_count = (*stage[:3], stage[3] + 1)
            self.assertEqual(workbench.check_stage(root, changed_count)["status"], "invalid")

    def test_one_broken_stage_invalidates_all(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = fixture(root)
            missing = ("missing", "missing", "0" * 64, 1)
            report = workbench.check_snapshots(root, [good, missing])
            self.assertEqual(report["status"], "invalid")
            self.assertEqual(len(report["stages"]), 2)
            self.assertEqual(report["stages"][0]["status"], "matched_snapshot")


class DispatchTests(unittest.TestCase):
    def test_broken_snapshot_prevents_any_execution(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(workbench.subprocess, "run") as launch:
            with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()) as stdout:
                code = workbench.report_command(Path(temporary), "json", [("missing", "missing", "0" * 64, 1)])
            self.assertEqual(code, 2)
            self.assertEqual(stdout.getvalue(), "")
            launch.assert_not_called()

    def test_missing_numpy_does_not_install_or_start_report(self):
        with patch.object(workbench, "check_snapshots", return_value={"status": "matched_snapshot"}), \
             patch.object(workbench.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "missing")) as launch:
            with redirect_stderr(io.StringIO()) as stderr, redirect_stdout(io.StringIO()) as stdout:
                code = workbench.report_command(ROOT, "json")
            self.assertEqual(code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("NumPy", stderr.getvalue())
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(launch.call_args.args[0][-1], "import numpy")

    def test_report_failure_discards_partial_output(self):
        responses = [subprocess.CompletedProcess([], 0, "", ""), subprocess.CompletedProcess([], 2, "partial-success", "rejected")]
        with patch.object(workbench, "check_snapshots", return_value={"status": "matched_snapshot"}), \
             patch.object(workbench.subprocess, "run", side_effect=responses) as launch:
            with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
                code = workbench.report_command(ROOT, "json")
            self.assertEqual(code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "rejected")
            command = launch.call_args.args[0]
            self.assertEqual(command[:3], [sys.executable, "-I", "-B"])
            self.assertEqual(command[-2:], ["--format", "json"])

    def test_success_forwards_selected_format_without_extra_text(self):
        responses = [subprocess.CompletedProcess([], 0, "", ""), subprocess.CompletedProcess([], 0, "# Evidence\n", "")]
        with patch.object(workbench, "check_snapshots", return_value={"status": "matched_snapshot"}), \
             patch.object(workbench.subprocess, "run", side_effect=responses) as launch:
            with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
                code = workbench.report_command(ROOT, "markdown")
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "# Evidence\n")
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(launch.call_args.args[0][-2:], ["--format", "markdown"])

    def test_invalid_check_json_and_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = fixture(root)
            (root / "demo/payload.txt").write_text("changed")
            with patch.object(workbench, "ROOT", root), patch.object(workbench, "STAGES", (stage,)):
                with redirect_stdout(io.StringIO()) as stdout:
                    code = workbench.main(["check", "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "invalid")


class RealCommandTests(unittest.TestCase):
    def command(self, *arguments, optimized=False):
        with tempfile.TemporaryDirectory() as temporary:
            return subprocess.run([sys.executable, "-I", "-S", *(["-O"] if optimized else []),
                                   str(ROOT / "workbench.py"), *arguments],
                                  cwd=temporary, capture_output=True, text=True, check=False)

    def test_list_without_site_packages_from_other_directory(self):
        result = self.command("list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "not_checked")
        self.assertEqual(len(payload["stages"]), 8)

    def test_all_checks_without_numpy_and_optimized_mode(self):
        normal = self.command("check", "--json")
        optimized = self.command("check", "--json", optimized=True)
        self.assertEqual(normal.returncode, 0, normal.stderr)
        self.assertEqual(normal.stdout, optimized.stdout)
        payload = json.loads(normal.stdout)
        self.assertEqual(payload["verified_artifacts"], 1186)
        self.assertEqual(payload["status"], "matched_snapshot")
        self.assertEqual(payload["engineering_release"], "not_supported")

    def test_single_stage(self):
        result = self.command("check", "radiation", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["verified_artifacts"], 25)

    def test_unknown_stage_rejected(self):
        result = self.command("check", "../../outside")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
