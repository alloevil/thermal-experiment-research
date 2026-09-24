import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import replay_thermal


class ReplayTests(unittest.TestCase):
    def test_prepare_does_not_copy_previous_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = replay_thermal.prepare(Path(temporary) / "科学 replay")
            self.assertTrue((output / "reference-experiment.json").is_file())
            self.assertEqual([path.name for path in (output / "results").iterdir()], ["protocol-sha256.txt"])
            for entry in json.loads((output / "source-receipt.json").read_text())["files"]:
                self.assertEqual(replay_thermal.sha256(output / entry["file"]), entry["sha256"])

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            marker = output / "mine"
            marker.write_text("keep")
            with self.assertRaisesRegex(ValueError, "already exists"):
                replay_thermal.prepare(output)
            self.assertEqual(marker.read_text(), "keep")

    def test_archived_study_output_rejected(self):
        with self.assertRaisesRegex(ValueError, "archived"):
            replay_thermal.prepare(ROOT / "radiation/new-replay-output")
        self.assertFalse((ROOT / "radiation/new-replay-output").exists())

    def test_missing_dependency_does_not_create_output_or_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "new"
            with patch.object(replay_thermal.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "missing")) as launch:
                with redirect_stderr(io.StringIO()) as error:
                    result = replay_thermal.main(["--python", sys.executable, "--output", str(output)])
            self.assertEqual(result, 2)
            self.assertFalse(output.exists())
            self.assertEqual(launch.call_count, 1)
            self.assertIn("nothing was installed", error.getvalue())

    def test_wrong_versions_rejected(self):
        metadata = json.dumps({"numpy": "0.0", "scipy": "0.0"})
        with tempfile.TemporaryDirectory() as temporary, patch.object(replay_thermal.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, metadata, "")):
            output = Path(temporary) / "new"
            with redirect_stderr(io.StringIO()):
                result = replay_thermal.main(["--python", sys.executable, "--output", str(output)])
            self.assertEqual(result, 2)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
