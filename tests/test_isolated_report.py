import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import verify_isolated_report as audit
from test_workbench import fixture


class IsolatedAuditTests(unittest.TestCase):
    def setup_source(self, root):
        stage = fixture(root)
        (root / "workbench.py").write_text("print('fixture')\n")
        (root / "tests").mkdir()
        (root / "tests/test_workbench.py").write_text("pass\n")
        (root / "demo/.venv").mkdir()
        (root / "demo/.venv/do-not-copy").write_text("environment")
        (root / "untracked.txt").write_text("not evidence")
        return stage

    def test_copy_only_pinned_files_and_explicit_entrypoints(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            stage = self.setup_source(source)
            destination = root / "副本 with spaces"
            with patch.object(audit, "STAGES", (stage,)):
                count = audit.copy_snapshot(source, destination)
            self.assertEqual(count, 4)
            self.assertFalse((destination / "demo/.venv").exists())
            self.assertFalse((destination / "untracked.txt").exists())
            self.assertEqual((destination / "demo/payload.txt").read_bytes(), (source / "demo/payload.txt").read_bytes())

    def test_corrupt_source_is_rejected_before_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            stage = self.setup_source(source)
            (source / "demo/payload.txt").write_text("changed")
            destination = root / "target"
            with patch.object(audit, "STAGES", (stage,)), self.assertRaisesRegex(RuntimeError, "invalid"):
                audit.copy_snapshot(source, destination)
            self.assertFalse(destination.exists())

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "existing"
            destination.mkdir()
            marker = destination / "mine"
            marker.write_text("keep")
            with self.assertRaisesRegex(RuntimeError, "already exist"):
                audit.copy_snapshot(root / "absent", destination)
            self.assertEqual(marker.read_text(), "keep")

    def test_requires_explicit_install_opt_in(self):
        with patch.object(audit.subprocess, "run") as execute, self.assertRaisesRegex(RuntimeError, "allow-install"):
            audit.main([])
        execute.assert_not_called()

    def test_environment_drops_python_and_environment_inheritance(self):
        with patch.dict(os.environ, {"PYTHONPATH": "/untrusted", "PYTHONHOME": "/other", "VIRTUAL_ENV": "/old", "CONDA_PREFIX": "/old-conda", "TZ": "other"}, clear=True):
            cleaned = audit.clean_environment()
            self.assertEqual(os.environ["PYTHONPATH"], "/untrusted")
        self.assertNotIn("PYTHONPATH", cleaned)
        self.assertNotIn("PYTHONHOME", cleaned)
        self.assertNotIn("VIRTUAL_ENV", cleaned)
        self.assertNotIn("CONDA_PREFIX", cleaned)
        self.assertEqual(cleaned["TZ"], "UTC")

    def test_report_lock_has_one_hash_pinned_requirement(self):
        text = (ROOT / "requirements-report.lock").read_text()
        requirements = [line for line in text.splitlines() if line and not line.startswith(("#", " "))]
        self.assertEqual(requirements, ["numpy==2.5.3 \\"])
        self.assertIn("--hash=sha256:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
