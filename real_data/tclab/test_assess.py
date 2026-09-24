import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from assess import assess, local_information, metrics, sensitivity_matrix
from diagnose import HEADERS, SETPOINTS
from thermal_model import INITIAL, LOWER, UPPER, ROOT, load_data, rollout


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / 'record.csv'
        self.times = np.arange(10, dtype=float) * 10
        self.inputs = np.array([[20, 10], [20, 10], [50, 10], [50, 40], [30, 40],
                                [30, 20], [70, 20], [70, 50], [0, 50], [0, 0]], float)

    def write(self, inputs=None, initial=None, parameters=None, setpoints=False):
        inputs = self.inputs if inputs is None else inputs
        prediction = rollout(self.times, inputs, [21, 20] if initial is None else initial,
                             INITIAL if parameters is None else parameters)['temperature_C']
        rows = np.column_stack([self.times, inputs, prediction])
        if setpoints:
            rows = np.column_stack([rows, np.full((len(rows), 2), 23.)])
        self.write_rows(rows, setpoints)
        return rows

    def write_rows(self, rows, setpoints=False):
        with self.path.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADERS + SETPOINTS if setpoints else HEADERS)
            writer.writerows(rows)

    def test_synthetic_recovery_and_independent_metric_recalculation(self):
        expected = np.array([12., .012, .009])
        self.write(parameters=expected)
        target = self.directory / 'result'
        result = assess(self.path, 60, target, True)
        np.testing.assert_allclose(result['fit']['parameters'], expected, rtol=2e-4)
        with (target / 'prediction.csv').open() as stream:
            table = list(csv.reader(stream))
        numeric = np.asarray(table[1:], float)
        training = numeric[:, 1] == 1
        for label, mask in [('training', training), ('validation', ~training)]:
            error = numeric[mask, 4:6] - numeric[mask, 2:4]
            self.assertAlmostEqual(result[f'{label}_metrics']['rmse_C'], float(np.sqrt(np.mean(error**2))))
        self.assertEqual(result['fit_sha256'], hashlib.sha256((target / 'fit.json').read_bytes()).hexdigest())
        self.assertEqual(result['precision_status'], 'not_established')
        self.assertEqual(result['hardware_action'], 'none')

    def test_holdout_temperature_cannot_change_fit_or_diagnosis(self):
        rows = self.write()
        first = assess(self.path, 60, self.directory / 'first', True)
        rows[6:, 3:5] += 3
        self.write_rows(rows)
        second = assess(self.path, 60, self.directory / 'second', True)
        self.assertEqual(first['fit'], second['fit'])
        self.assertEqual(first['local_information'], second['local_information'])
        self.assertEqual(first['next_steps'], second['next_steps'])
        self.assertGreater(second['validation_metrics']['rmse_C'], first['validation_metrics']['rmse_C'] + 2)
        first_predictions = np.loadtxt(self.directory / 'first/prediction.csv', delimiter=',', skiprows=1)[:, 4:]
        second_predictions = np.loadtxt(self.directory / 'second/prediction.csv', delimiter=',', skiprows=1)[:, 4:]
        np.testing.assert_array_equal(first_predictions, second_predictions)

    def test_future_inputs_do_not_enter_fit(self):
        rows = self.write()
        first = assess(self.path, 60, self.directory / 'first', True)
        rows[6:, 1:3] = 0
        self.write_rows(rows)
        second = assess(self.path, 60, self.directory / 'second', True)
        self.assertEqual(first['fit'], second['fit'])
        self.assertEqual(first['local_information'], second['local_information'])

    def test_terminal_command_does_not_estimate_unexcited_gain(self):
        inputs = self.inputs.copy()
        inputs[:5, 1] = 0
        inputs[5:, 1] = 50
        self.write(inputs)
        result = assess(self.path, 60, self.directory / 'result', True)
        self.assertEqual(result['fit']['fixed_unexcited_parameters'], ['alpha2'])
        self.assertEqual(result['fit']['parameters'][2], INITIAL[2])
        self.assertEqual(result['local_information']['rms_sensitivity_C_per_range'][2], 0)
        self.assertEqual(len(result['unexcited_assumption_checks']), 2)
        for item in result['unexcited_assumption_checks']:
            self.assertLess(item['training_max_difference_C'], 1e-7)
            self.assertGreater(item['validation_max_prediction_difference_C'], 0)

    def test_unexcited_first_gain_is_also_fixed(self):
        inputs = self.inputs.copy()
        inputs[:, 0] = 0
        self.write(inputs)
        result = assess(self.path, 60, self.directory / 'result', True)
        self.assertEqual(result['fit']['fixed_unexcited_parameters'], ['alpha1'])
        self.assertEqual(result['local_information']['rms_sensitivity_C_per_range'][1], 0)

    def test_equilibrium_has_no_parameter_information(self):
        self.write(np.zeros_like(self.inputs), [23, 23])
        result = assess(self.path, 60, self.directory / 'result', True)
        self.assertTrue(result['fit']['optimizer_success'])
        self.assertEqual(result['fit']['fixed_unexcited_parameters'], ['alpha1', 'alpha2'])
        self.assertEqual(result['local_information']['numerical_rank'], 0)
        self.assertIsNone(result['local_information']['condition_number'])
        self.assertTrue(all(pair['cosine'] is None for pair in result['local_information']['column_cosines']))
        json.dumps(result, allow_nan=False)

    def test_zero_celsius_is_valid_for_new_objective(self):
        self.write(initial=[0, 0], setpoints=True)
        result = assess(self.path, 60, self.directory / 'result', True)
        self.assertLess(result['training_metrics']['rmse_C'], 1e-6)
        self.assertEqual(len(result['source']['columns']), 7)

    def test_range_scaling_and_boundary_difference(self):
        span = UPPER - LOWER

        def linear_rollout(times, inputs, initial, parameters):
            scaled = (parameters - LOWER) / span
            basis = np.array([[1, 2, 3], [4, 6, 5]], float)
            values = np.outer(times - times[0], basis @ scaled)
            return {'temperature_C': values}

        with patch('assess.rollout', side_effect=linear_rollout):
            for parameters in [LOWER, UPPER, INITIAL]:
                matrix = sensitivity_matrix(self.times, self.inputs, [23, 23], parameters, 1e-4)
                expected = np.concatenate([elapsed * np.array([[1, 2, 3], [4, 6, 5]]) for elapsed in self.times[1:]])
                np.testing.assert_allclose(matrix, expected, rtol=1e-9, atol=1e-9)

    def test_actual_finite_difference_refinement(self):
        information, fine, coarse = local_information(self.times, self.inputs, [21, 20], INITIAL)
        self.assertLess(information['step_refinement_relative_difference'], 1e-3)
        np.testing.assert_allclose(fine, coarse, rtol=1e-3, atol=1e-6)
        self.assertEqual(fine.shape, (18, 3))

    def test_failed_optimizer_retains_fit_but_no_report(self):
        self.write()
        result = SimpleNamespace(success=False, message='Evaluation budget exhausted', x=INITIAL * [1, 1000, 1000],
                                 active_mask=np.array([0, 0, 0]), nfev=100, fun=np.array([1.]))
        target = self.directory / 'failed'
        with patch('assess.least_squares', return_value=result), self.assertRaisesRegex(ValueError, 'did not converge'):
            assess(self.path, 60, target, True)
        self.assertFalse(json.loads((target / 'fit.json').read_text())['optimizer_success'])
        self.assertEqual(json.loads((target / 'status.json').read_text())['status'], 'FAILED')
        self.assertFalse((target / 'report.json').exists())

    def test_invalid_selection_and_missing_acceptance_leave_no_directory(self):
        self.write()
        for cutoff, accepted in [(60, False), (0, True), (float('nan'), True), (20, True), (100, True)]:
            target = self.directory / 'invalid'
            with self.subTest(cutoff=cutoff, accepted=accepted), self.assertRaises(ValueError):
                assess(self.path, cutoff, target, accepted)
            self.assertFalse(target.exists())

    def test_existing_output_and_symlink_are_not_overwritten(self):
        self.write()
        existing = self.directory / 'existing'
        existing.mkdir()
        link = self.directory / 'dangling'
        link.symlink_to(self.directory / 'missing')
        for target in [existing, link, self.path]:
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'Output exists'):
                assess(self.path, 60, target, True)
        self.assertTrue(link.is_symlink())
        self.assertEqual(list(existing.iterdir()), [])

    def test_cli_other_directory_preserves_input_and_requires_acceptance(self):
        self.write()
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
        command = [sys.executable, '-B', '-O', str(ROOT / 'assess.py'), '--data', str(self.path),
                   '--before-seconds', '60', '--output', str(self.directory / 'cli')]
        rejected = subprocess.run(command, cwd=self.directory, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected.stdout, '')
        completed = subprocess.run(command + ['--accept-model-assumptions'], cwd=self.directory,
                                   capture_output=True, text=True, check=True)
        self.assertIn('不支持工程放行', completed.stdout)
        self.assertEqual(before, (self.path.read_bytes(), self.path.stat().st_mtime_ns))
        self.assertEqual(json.loads((self.directory / 'cli/status.json').read_text())['status'], 'COMPLETED')


class RecordedAssessmentTests(unittest.TestCase):
    def test_recompute_measured_assessments_and_check_provenance(self):
        data = load_data()
        for cutoff in [100, 300]:
            with self.subTest(cutoff=cutoff):
                directory = ROOT / f'assessment_examples/before-{cutoff}'
                report = json.loads((directory / 'report.json').read_text())
                config = json.loads((directory / 'run-config.json').read_text())
                self.assertEqual(json.loads((directory / 'status.json').read_text())['status'], 'COMPLETED')
                for name, expected in config['source_hashes'].items():
                    self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected, name)
                self.assertEqual(report['source']['sha256'], hashlib.sha256((ROOT / 'upstream/data.txt').read_bytes()).hexdigest())
                self.assertEqual(report['fit_sha256'], hashlib.sha256((directory / 'fit.json').read_bytes()).hexdigest())
                self.assertEqual(report['fit'], json.loads((directory / 'fit.json').read_text()))
                table = np.loadtxt(directory / 'prediction.csv', delimiter=',', skiprows=1)
                training = data[:, 0] < cutoff
                np.testing.assert_array_equal(table[:, 0], data[:, 0])
                np.testing.assert_array_equal(table[:, 1], training)
                np.testing.assert_array_equal(table[:, 2:4], data[:, 3:5])
                parameters = np.asarray(report['fit']['parameters'])
                predicted = rollout(data[:, 0], data[:, 1:3], data[0, 3:5], parameters)['temperature_C']
                np.testing.assert_allclose(table[:, 4:6], predicted, atol=1e-9, rtol=0)
                for label, mask in [('training', training), ('validation', ~training)]:
                    recalculated = metrics(predicted[mask], data[mask, 3:5])
                    for key, value in recalculated.items():
                        np.testing.assert_allclose(report[f'{label}_metrics'][key], value, atol=1e-9, rtol=0)
                start = int(training.sum()) - 1
                continuation = rollout(data[start:, 0], data[start:, 1:3], predicted[start], parameters)['temperature_C']
                np.testing.assert_allclose(continuation, predicted[start:], atol=1e-9, rtol=0)
                fine = sensitivity_matrix(data[training, 0], data[training, 1:3], data[0, 3:5], parameters, 5e-5)
                with np.load(directory / 'local-sensitivity.npz', allow_pickle=False) as saved:
                    np.testing.assert_array_equal(saved['parameters'], parameters)
                    np.testing.assert_array_equal(saved['training_time'], data[training, 0][1:])
                    np.testing.assert_allclose(saved['fine'], fine, atol=1e-7, rtol=1e-7)
                singular = np.linalg.svd(fine, compute_uv=False)
                np.testing.assert_allclose(report['local_information']['singular_values'], singular, atol=1e-7, rtol=1e-7)
                self.assertEqual(report['local_information']['numerical_rank'], int(np.linalg.matrix_rank(fine)))
                self.assertEqual(report['precision_status'], 'not_established')
                self.assertEqual(report['engineering_release'], 'not_supported')


if __name__ == '__main__':
    unittest.main(verbosity=2)
