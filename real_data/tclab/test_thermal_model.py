import json
import shutil
import tempfile
import unittest
from pathlib import Path

from thermal_model import (ROOT, INITIAL, CAPACITY_J_K, AMBIENT_C, fluxes,
                           load_data, np, rollout)


class ThermalDataTests(unittest.TestCase):
    def test_actual_file_units_and_split(self):
        data = load_data()
        self.assertEqual(data.shape, (599, 7))
        self.assertEqual(np.count_nonzero(data[:, 0] < 100), 100)
        self.assertEqual(np.count_nonzero(data[:, 0] < 300), 300)
        self.assertTrue(np.all(data[data[:, 0] < 100, 2] == 0))
        self.assertGreater(np.max(data[data[:, 0] < 300, 2]), 0)

    def test_rejects_bad_units_duplicate_time_and_nonfinite(self):
        lines = (ROOT / 'upstream/data.txt').read_text().splitlines()[:4]
        variants = []
        variant = lines.copy()
        variant[0] = variant[0].replace('degC', 'Kelvin')
        variants.append(variant)
        variant = lines.copy()
        fields = variant[2].split(',')
        fields[0] = variant[1].split(',')[0]
        variant[2] = ','.join(fields)
        variants.append(variant)
        variant = lines.copy()
        fields = variant[1].split(',')
        fields[3] = 'NaN'
        variant[1] = ','.join(fields)
        variants.append(variant)
        for rows in variants:
            with self.subTest(rows=rows[0]), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / 'bad.csv'
                path.write_text('\n'.join(rows))
                with self.assertRaises(ValueError):
                    load_data(path)

    def test_equilibrium_and_exchange_cancellation(self):
        for coupled in [True, False]:
            net, *_ = fluxes([AMBIENT_C, AMBIENT_C], [0, 0], INITIAL, coupled)
            np.testing.assert_array_equal(net, [0, 0])
        coupled, absorbed, convection, radiation = fluxes([60, 30], [60, 20], INITIAL, True)
        independent, *_ = fluxes([60, 30], [60, 20], INITIAL, False)
        self.assertAlmostEqual(coupled.sum(), independent.sum())
        self.assertAlmostEqual(coupled.sum(), (absorbed - convection - radiation).sum())

    def test_inputs_are_left_held_and_targets_not_reset(self):
        times = np.array([0., 1., 2.])
        inputs = np.array([[0., 0.], [100., 0.], [0., 0.]])
        result = rollout(times, inputs, [23, 23], INITIAL, False)['temperature_C']
        np.testing.assert_allclose(result[1], [23, 23], atol=1e-12)
        self.assertGreater(result[2, 0], 23)
        changed_final_input = inputs.copy()
        changed_final_input[-1] = [100, 100]
        other = rollout(times, changed_final_input, [23, 23], INITIAL, False)['temperature_C']
        np.testing.assert_allclose(result, other, rtol=0, atol=1e-12)

    def test_unexcited_gain_is_unobservable(self):
        times = np.linspace(0, 80, 9)
        inputs = np.tile([70., 0.], (len(times), 1))
        lower, upper = INITIAL.copy(), INITIAL.copy()
        lower[2], upper[2] = .002, .015
        for coupled in [True, False]:
            first = rollout(times, inputs, [20.83, 19.93], lower, coupled)['temperature_C']
            second = rollout(times, inputs, [20.83, 19.93], upper, coupled)['temperature_C']
            np.testing.assert_allclose(first, second, rtol=0, atol=1e-12)

    def test_independent_second_node_ignores_first_heater(self):
        times = np.linspace(0, 80, 9)
        cold = np.zeros((len(times), 2))
        hot = cold.copy()
        hot[:, 0] = 100
        first = rollout(times, cold, [20, 20], INITIAL, False)['temperature_C']
        second = rollout(times, hot, [20, 20], INITIAL, False)['temperature_C']
        np.testing.assert_allclose(first[:, 1], second[:, 1], atol=1e-7, rtol=0)

    def test_ledger_and_input_validation(self):
        times = np.array([0, 1, 3, 7], float)
        inputs = np.array([[100, 0], [100, 20], [0, 20], [0, 0]], float)
        result = rollout(times, inputs, [21, 20], INITIAL, ledger=True)
        stored = CAPACITY_J_K * (result['temperature_C'] - [21, 20]).sum(axis=1)
        ledger = result['ledger_J']
        np.testing.assert_allclose(stored, ledger[:, 0] - ledger[:, 1] - ledger[:, 2], atol=1e-9)
        with self.assertRaises(ValueError):
            rollout(times[::-1], inputs, [21, 20], INITIAL)
        with self.assertRaises(ValueError):
            rollout(times, inputs * 2, [21, 20], INITIAL)


class RecordedResultChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / 'results'
        shutil.copytree(ROOT / 'results/locked-run', self.directory)

    def test_recorded_study_verifies(self):
        from verify_and_plot import verify

        result = verify(self.directory)
        self.assertEqual(len(result['comparisons']), 4)

    def test_prediction_tampering_rejected(self):
        from verify_and_plot import verify

        path = self.directory / 'coupled-train-100/prediction.npz'
        with np.load(path) as source:
            data = {key: source[key].copy() for key in source.files}
        data['predicted_C'][200, 1] += 10
        np.savez_compressed(path, **data)
        with self.assertRaisesRegex(ValueError, 'RMSE'):
            verify(self.directory)

    def test_training_mask_tampering_rejected(self):
        from verify_and_plot import verify

        path = self.directory / 'coupled-train-100/prediction.npz'
        with np.load(path) as source:
            data = {key: source[key].copy() for key in source.files}
        data['training_mask'][100] = True
        np.savez_compressed(path, **data)
        with self.assertRaises(AssertionError):
            verify(self.directory)

    def test_frozen_fit_tampering_rejected(self):
        from verify_and_plot import verify

        path = self.directory / 'coupled-train-100/fit.json'
        record = json.loads(path.read_text())
        record['parameters'][2] = .003
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'Fit changed'):
            verify(self.directory)


if __name__ == '__main__':
    unittest.main(verbosity=2)
