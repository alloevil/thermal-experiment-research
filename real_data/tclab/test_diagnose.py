import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from diagnose import HEADERS, SETPOINTS, analyze, main, markdown, read_record

ROOT = Path(__file__).resolve().parent


class DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "measurements.csv"

    def write(self, rows, header=None):
        with self.path.open("w", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(HEADERS if header is None else header)
            writer.writerows(rows)

    def test_real_prefixes(self):
        source = ROOT / "upstream/data.txt"
        first = analyze(source, 100)
        later = analyze(source, 300)
        self.assertEqual(first["selection"]["rows_used"], 100)
        self.assertEqual(first["selection"]["intervals_used"], 99)
        self.assertEqual(first["parameters_without_input_information"], ["alpha2"])
        self.assertEqual(first["channels"][1]["nonzero_duration_s"], 0)
        self.assertEqual(later["selection"]["rows_used"], 300)
        self.assertEqual(later["parameters_without_input_information"], [])
        self.assertEqual(later["status"], "no_zero_input_obstruction_found")
        self.assertEqual(later["engineering_release"], "not_supported")

    def test_last_row_activation_not_counted(self):
        self.write([[0, 10, 0, 23, 23], [1, 10, 0, 24, 23], [3, 10, 50, 25, 23]])
        result = analyze(self.path)
        second = result["channels"][1]
        self.assertEqual(second["status"], "no_input_information")
        self.assertTrue(second["last_row_changed_without_followup"])
        self.assertEqual(second["input_integral_percent_seconds"], 0)

    def test_irregular_time_integral_and_transition_count(self):
        self.write([[0, 10, 0, 23, 23], [2, 20, 0, 24, 23], [5, 30, 0, 25, 23], [9, 0, 0, 26, 23]])
        channel = analyze(self.path)["channels"][0]
        self.assertEqual(channel["input_integral_percent_seconds"], 10 * 2 + 20 * 3 + 30 * 4)
        self.assertEqual(channel["nonzero_duration_s"], 9)
        self.assertEqual(channel["observed_input_changes"], 2)

    def test_constant_input_is_not_declared_unidentifiable(self):
        self.write([[0, 30, 40, 23, 24], [1, 30, 40, 24, 25], [2, 30, 40, 25, 26]])
        result = analyze(self.path)
        self.assertEqual(result["parameters_without_input_information"], [])
        self.assertTrue(all(item["constant_nonzero_input"] for item in result["channels"]))

    def test_tiny_nonzero_is_not_exact_zero(self):
        self.write([[0, 1e-20, 0, 23, 23], [1, 1e-20, 0, 23, 23]])
        first = analyze(self.path)["channels"][0]
        self.assertEqual(first["status"], "not_ruled_out_by_zero_input_check")

    def test_identical_inputs_only_descriptive(self):
        self.write([[0, 20, 20, 23, 23], [1, 30, 30, 24, 24], [2, 0, 50, 25, 25]])
        result = analyze(self.path)
        self.assertTrue(result["identical_observed_inputs"])
        self.assertEqual(result["parameters_without_input_information"], [])

    def test_both_zero_and_nonzero_initial_time(self):
        self.write([[10, 0, 0, 21, 20], [12, 0, 0, 21, 20]])
        result = analyze(self.path)
        self.assertEqual(result["parameters_without_input_information"], ["alpha1", "alpha2"])
        self.assertEqual(result["selection"]["duration_s"], 2)

    def test_cutoff_is_exclusive_and_no_future_contribution(self):
        self.write([[0, 10, 0, 23, 23], [1, 10, 0, 24, 23], [2, 0, 50, 25, 25], [3, 0, 50, 26, 27]])
        initial = analyze(self.path, 2)
        self.assertEqual(initial["selection"]["rows_used"], 2)
        self.assertEqual(initial["parameters_without_input_information"], ["alpha2"])
        for cutoff in [0, -1, .5, float("nan"), float("inf")]:
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                analyze(self.path, cutoff)

    def test_five_and_seven_columns_and_bom(self):
        self.write([[0, 0, 0, 20, 21, 23, 23], [1, 10, 0, 21, 22, 23, 23]], HEADERS + SETPOINTS)
        content = self.path.read_text()
        self.path.write_text("\ufeff" + content)
        rows, provenance = read_record(self.path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(provenance["columns"]), 7)

    def test_invalid_data_is_rejected(self):
        invalid = [
            [[0, 0, 0, 23, 23]],
            [[0, 0, 0, 23, 23], [0, 10, 0, 24, 23]],
            [[0, 0, 0, 23, 23], [1, 101, 0, 24, 23]],
            [[0, 0, 0, 23, 23], [1, 10, 0, "NaN", 23]],
            [[0, 0, 0, 23, 23], [1, 10, 0, 24, float("inf")]],
            [[0, 0, 0, 23, 23], [1, 10, 0, -273.15, 23]],
            [[0, 0, 0, 23, 23], [1, 10, 0, 24]],
            [[-1, 0, 0, 23, 23], [1, 10, 0, 24, 23]],
        ]
        for rows in invalid:
            with self.subTest(rows=rows):
                self.write(rows)
                with self.assertRaises(ValueError):
                    analyze(self.path)
        self.path.write_text("")
        with self.assertRaises(ValueError):
            analyze(self.path)

    def test_units_are_not_guessed(self):
        for replacement in ["Temperature 1 (K)", "Temperature 1", "Temperature 2 (degC)"]:
            header = HEADERS.copy()
            header[3] = replacement
            self.write([[0, 0, 0, 23, 23], [1, 1, 1, 24, 24]], header)
            with self.assertRaises(ValueError):
                analyze(self.path)

    def test_non_equilibrium_is_not_diagnosed_as_bias(self):
        self.write([[0, 0, 0, 20, 25], [1, 0, 0, 21, 24]])
        result = analyze(self.path)
        self.assertEqual(result["initial_T1_minus_T2_C"], -5)
        self.assertIn("not proof", result["initial_state_note"])
        self.assertIn("不支持工程放行", markdown(result))
        self.assertEqual(result["hardware_action"], "none")

    def test_cli_invalid_input_has_no_success_output(self):
        self.path.write_text("bad header\n")
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as error:
            result = main(["--data", str(self.path), "--format", "json"])
        self.assertEqual(result, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertTrue(error.getvalue())

    def test_cli_other_directory_no_site_packages_and_read_only(self):
        source = ROOT / "upstream/data.txt"
        before = (source.stat().st_mtime_ns, hashlib.sha256(source.read_bytes()).hexdigest())
        arguments = ["--data", str(source), "--before-seconds", "100", "--format", "json"]
        first = subprocess.run([sys.executable, "-I", "-S", "-B", str(ROOT / "diagnose.py"), *arguments],
                               cwd=self.temporary.name, capture_output=True, text=True, check=True)
        optimized = subprocess.run([sys.executable, "-I", "-S", "-B", "-O", str(ROOT / "diagnose.py"), *arguments],
                                   cwd=self.temporary.name, capture_output=True, text=True, check=True)
        self.assertEqual(first.stdout, optimized.stdout)
        self.assertEqual(json.loads(first.stdout)["parameters_without_input_information"], ["alpha2"])
        self.assertEqual(before, (source.stat().st_mtime_ns, hashlib.sha256(source.read_bytes()).hexdigest()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
