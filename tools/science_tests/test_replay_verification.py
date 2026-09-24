import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from check_thermal_replay import verify


class RecomputedArrayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "replay"
        source = ROOT / "tools/results/thermal-replay"
        self.directory.mkdir()
        shutil.copytree(source / "results", self.directory / "results")
        shutil.copyfile(source / "reference-experiment.json", self.directory / "reference-experiment.json")

    def mutate_array(self, filename, operation):
        path = self.directory / "results" / filename
        with np.load(path, allow_pickle=False) as source:
            arrays = {name: source[name].copy() for name in source.files}
        operation(arrays)
        np.savez(path, **arrays)

    def test_new_result_matches_frozen_reference(self):
        result = verify(self.directory)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["new_solver_calls"], 191)

    def test_modified_field_is_not_accepted(self):
        self.mutate_array("optimized.npz", lambda arrays: arrays["temperature"].__iadd__(.2))
        with self.assertRaisesRegex(ValueError, "Mismatch"):
            verify(self.directory)

    def test_excess_power_is_rejected(self):
        def change(arrays):
            arrays["powers"][1, 0] = 1.5
        self.mutate_array("optimized.npz", change)
        with self.assertRaisesRegex(ValueError, "Power violation"):
            verify(self.directory)

    def test_false_feasibility_label_is_rejected(self):
        path = self.directory / "results/experiment.json"
        data = json.loads(path.read_text())
        data["baseline"]["feasible_at_sampled_points"] = True
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "Feasibility label"):
            verify(self.directory)

    def test_broken_energy_ledger_is_rejected(self):
        def change(arrays):
            arrays["ledger"][-1, 0] += 1
        self.mutate_array("optimized.npz", change)
        with self.assertRaisesRegex(ValueError, "Energy conservation"):
            verify(self.directory)

    def test_different_input_invalidates_radiation_comparison(self):
        def change(arrays):
            arrays["powers"][-1, 0] += .01
        self.mutate_array("linear-radiation.npz", change)
        with self.assertRaises(ValueError):
            verify(self.directory)


if __name__ == "__main__":
    unittest.main(verbosity=2)
