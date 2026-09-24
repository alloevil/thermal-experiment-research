import copy
import json
import tempfile
import unittest
from pathlib import Path

from core import ExperimentBank, add_measurement, example_case, numeric_array, simulate, validate_case, np
from cli import load, new_directory


def record(name="initial", values=None, identifier="first"):
    return {"id": identifier, "experiment": name, "values_K": [300.] if values is None else values}


def small_case():
    case = example_case()
    case["grid"] = {"convection": [1, 1.4], "offset_K": [0, -.6], "gain": [1.], "capacity": [1.]}
    return case


class CoreTests(unittest.TestCase):
    def test_likelihood_matches_direct_bayes(self):
        bank = ExperimentBank(small_case())
        bank.predictions["initial"] = np.array([[300.], [299.], [300.], [299.5]])
        summary, weights = bank.posterior({"records": [record(values=[299.4])]})
        expected = np.exp(-.5 * ((bank.predictions["initial"][:, 0] - 299.4) / .25)**2) / 4
        expected /= expected.sum()
        np.testing.assert_allclose(weights, expected)
        self.assertAlmostEqual(summary["model_probability"]["convection"], sum(expected[:2]))

    def test_order_invariance(self):
        bank = ExperimentBank(small_case())
        bank.predictions["initial"] = np.array([[300.], [299.], [300.], [299.5]])
        data = [record(values=[299.4]), record(values=[299.3], identifier="second")]
        first, left = bank.posterior({"records": data})
        second, right = bank.posterior({"records": data[::-1]})
        np.testing.assert_allclose(left, right)
        self.assertEqual(first["status"], second["status"])

    def test_bad_data_cannot_force_two_way_classification(self):
        bank = ExperimentBank(small_case())
        bank.predictions["initial"] = np.full((4, 1), 300.)
        result = bank.recommend({"records": [record(values=[400.])]})
        self.assertEqual(result["status"], "unsupported")
        self.assertIsNone(result["recommendation"])

    def test_identical_models_abstain(self):
        case = small_case()
        case["grid"]["convection"] = [1]
        case["grid"]["offset_K"] = [0]
        bank = ExperimentBank(case)
        for name, spec in case["experiments"].items():
            bank.predictions[name] = np.full((2, len(spec["observations"])), 300.)
        result = bank.recommend({"records": [record()]})
        self.assertEqual(result["status"], "not_distinguishable")
        self.assertLess(abs(result["options"][0]["expected_information_gain_nats"]), 1e-12)

    def test_information_gain_rewards_separation(self):
        bank = ExperimentBank(small_case())
        for name, spec in bank.case["experiments"].items():
            bank.predictions[name] = np.full((4, len(spec["observations"])), 300.)
        bank.predictions["heat_high"][2:] += 5
        _, weights = bank.posterior({"records": [record()]})
        ranking = bank.score_experiments(weights)
        self.assertEqual(ranking[0]["experiment"], "heat_high")
        self.assertAlmostEqual(ranking[0]["expected_information_gain_nats"], np.log(2))
        self.assertEqual(ranking, bank.score_experiments(weights))

    def test_disabled_over_budget_and_reference_not_assumed(self):
        case = small_case()
        case["budget"] = .5
        bank = ExperimentBank(case)
        bank.predictions["initial"] = np.full((4, 1), 300.)
        result = bank.recommend({"records": [record()]})
        self.assertEqual(result["status"], "no_available_experiment")
        case["experiments"]["reference"]["enabled"] = True
        with self.assertRaisesRegex(ValueError, "Reference"):
            validate_case(case)

    def test_predicted_temperature_screen(self):
        case = small_case()
        case["max_predicted_temperature_K"] = 300
        bank = ExperimentBank(case)
        bank.predictions["initial"] = np.full((4, 1), 300.)
        for name in ["heat_low", "heat_high", "cooldown"]:
            bank.predictions[name] = np.full((4, 3), 320.)
            bank.peak_temperatures[name] = 320.
        result = bank.recommend({"records": [record()]})
        self.assertEqual(result["status"], "no_available_experiment")
        self.assertEqual(len(result["excluded_experiments"]), 3)

    def test_update_preserves_input_and_rejects_duplicates(self):
        case = small_case()
        original = {"records": [record()]}
        copied = copy.deepcopy(original)
        measurement = record("heat_low", [300, 301, 302], "second")
        updated = add_measurement(case, original, measurement)
        self.assertEqual(original, copied)
        self.assertEqual(len(updated["records"]), 2)
        with self.assertRaisesRegex(ValueError, "unique"):
            add_measurement(case, updated, measurement)
        with self.assertRaises(ValueError):
            add_measurement(case, original, record("reference", [0], "reference"))

    def test_invalid_physics_and_data_rejected(self):
        for change in [lambda spec: spec["powers_W"].__setitem__(1, [4, 4, 4]),
                       lambda spec: spec["knots_s"].__setitem__(1, -1),
                       lambda spec: spec.__setitem__("sigma_K", 0),
                       lambda spec: spec["observations"].append(copy.deepcopy(spec["observations"][0]))]:
            case = small_case()
            change(case["experiments"]["heat_low"])
            with self.assertRaises(ValueError):
                validate_case(case)
        for values in [[float('nan')], [True], [float('inf')]]:
            with self.assertRaises(ValueError):
                numeric_array(values, "measurement")

    def test_duplicate_json_keys_and_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text('{"records":[],"records":[]}')
            with self.assertRaises(ValueError):
                load(path)
            with self.assertRaises(ValueError):
                new_directory(Path(directory))

    def test_reference_semantics_and_spatial_resolution(self):
        case = example_case()
        reference = case["experiments"]["reference"]
        np.testing.assert_array_equal(simulate(reference, offset=-.4), [-.4])
        for name in ["initial", "heat_low", "heat_high", "cooldown"]:
            coarse = simulate(case["experiments"][name], convection=1.4, gain=1.02, capacity=.98, cells=24)
            fine = simulate(case["experiments"][name], convection=1.4, gain=1.02, capacity=.98, cells=96)
            self.assertLess(float(np.max(abs(coarse - fine))), .05)


if __name__ == "__main__":
    unittest.main(verbosity=2)
