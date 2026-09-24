import ast
import hashlib
import json
import warnings
from dataclasses import replace
from pathlib import Path

from effective import (
    CALIBRATION_KNOTS, CALIBRATION_POWERS, SENSOR_POSITIONS, EffectiveModel,
    HeatingModel, Parameters, metrics, np, sensor_prediction, sensor_values, temperature_margins,
)
from model import target
from scipy.stats import qmc


ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(path.read_text())


def count_calls(path, expected):
    calls = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(calls) == expected
    assert [record["call"] for record in calls] == list(range(1, expected + 1))
    return calls


def verify_physical(path, factors, expected, samples=721):
    with np.load(path, allow_pickle=False) as trace:
        elapsed, temperature, ledger = trace["time"], trace["temperature"], trace["ledger"]
        assert len(elapsed) == samples and elapsed[0] == 0 and elapsed[-1] == 180
        assert np.isfinite(temperature).all() and temperature.min() > 0
        command, actual = trace["command_powers"], trace["actual_powers"]
        np.testing.assert_allclose(actual, command * factors["power_gain"], rtol=0, atol=0)
        assert command.min() >= -1e-9 and command.max() <= 1 / 1.1 + 1e-9
        assert np.max(abs(np.diff(command, axis=0) / 60)) <= 0.015 / 1.1 + 1e-9
        assert actual.min() >= -1e-9 and actual.max() <= 1 + 1e-9
        assert np.max(abs(np.diff(actual, axis=0) / 60)) <= 0.015 + 1e-9
        derived = {
            "mse_K2": float(np.trapezoid(np.mean((temperature - target(elapsed)[:, None])**2, axis=1), elapsed) / 180),
            "peak_K": float(temperature.max()), "max_spread_K": float(np.ptp(temperature, axis=1).max()),
            "final_mean_K": float(temperature[-1].mean()), "final_std_K": float(temperature[-1].std()),
        }
        for quantity, value in derived.items():
            assert np.isclose(value, expected[quantity], rtol=1e-10, atol=1e-10), (path, quantity)
        stored = Parameters().mass * Parameters().heat_capacity * factors["heat_capacity"] * (temperature.mean(axis=1) - Parameters().ambient)
        assert np.max(abs(stored - ledger[:, 0] + ledger[:, 1] + ledger[:, 2])) < 1e-4
        absorbed = np.trapezoid(actual.sum(axis=1), [0, 60, 120, 180])
        assert abs(absorbed - ledger[-1, 0]) < 1e-4
        convective = np.trapezoid(trace["convection"], elapsed)
        radiative = np.trapezoid(trace["radiation"], elapsed)
        assert abs(absorbed - convective - radiative - stored[-1]) < 0.1
        assert abs(convective - ledger[-1, 1]) < 0.1 and abs(radiative - ledger[-1, 2]) < 0.1
        assert expected["feasible"] == bool(min(temperature_margins(derived)) >= -1e-5)


def main():
    results = ROOT / "results"
    config, summary = read_json(results / "config.json"), read_json(results / "summary.json")
    for name, expected in config["hashes"].items():
        source = ROOT / name if "/" not in name else ROOT.parent / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, name
    for source in ROOT.glob("*.py"):
        compile(source.read_text(), str(source), "exec")
    functions = ast.parse((ROOT / "fit_and_control.py").read_text())
    fit_function = next(node for node in functions.body if isinstance(node, ast.FunctionDef) and node.name == "fit_ratios")
    assert [arg.arg for arg in fit_function.args.args] == ["observed_times", "observed_temperatures", "output_dir"]
    referenced = {node.id for node in ast.walk(fit_function) if isinstance(node, ast.Name)}
    assert not referenced.intersection({"factors", "true_ratios", "heldout_truth", "objects"})
    reconstructed = 0.9 + 0.2 * qmc.Sobol(5, scramble=True, seed=20260925).random_base2(3)
    factor_names = ["emissivity", "convection", "heat_capacity", "power_gain", "axial_conductance"]
    assert config["objects"] == [dict(zip(factor_names, row.tolist(), strict=True)) for row in reconstructed]
    previous_cases = read_json(ROOT.parent / "sensitivity/results/config.json")["cases"]
    previous_vectors = {tuple(case["factors"][name] for name in factor_names) for case in previous_cases}
    assert all(tuple(factors[name] for name in factor_names) not in previous_vectors for factors in config["objects"])
    assert read_json(results / "model-checks.json")["status"] == "PASS"
    nominal_control = read_json(results / "nominal-control/control.json")
    count_calls(results / "nominal-control/control-calls.jsonl", nominal_control["actual_solver_calls"])
    cases = []
    fit_calls, control_calls = 0, 0
    observation_reproduction = []
    fit_reproductions = []
    for object_index, factors in enumerate(config["objects"]):
        folder = results / f"object-{object_index}"
        with np.load(folder / "observations.npz") as observations:
            assert observations["noisy"].shape == (2, 48, 3)
            np.testing.assert_array_equal(observations["times"], np.arange(5, 241, 5))
            for replicate in range(2):
                generated = observations["clean"] + np.random.default_rng(20260925 + 100 * object_index + replicate).normal(0, 0.1, (48, 3))
                np.testing.assert_array_equal(observations["noisy"][replicate], generated)
            if object_index in [0, 7]:
                params = Parameters()
                physical = HeatingModel(96, parameters=replace(params, **{
                    name: getattr(params, name) * value for name, value in factors.items() if name != "power_gain"
                }))
                regenerated = physical.solve(CALIBRATION_POWERS * factors["power_gain"], knots=CALIBRATION_KNOTS,
                                             sample_step=5, rtol=1e-10, atol=1e-11)
                difference = float(np.max(abs(sensor_values(physical, regenerated)[1:] - observations["clean"])))
                assert difference < 1e-8
                observation_reproduction.append({"object": object_index, "max_difference_K": difference})
        nominal_physical = read_json(folder / "nominal-physical.json")
        verify_physical(folder / "nominal-physical.npz", factors, nominal_physical)
        for replicate in range(2):
            run_dir = folder / f"noise-{replicate}"
            case = read_json(run_dir / "case.json")
            assert case["object"] == object_index and case["noise_replicate"] == replicate
            assert case["fit_frozen_sha256"] == hashlib.sha256((run_dir / "fit.json").read_bytes()).hexdigest()
            assert case["fit"] == read_json(run_dir / "fit.json")
            assert case["control"] == read_json(run_dir / "control.json")
            actual_fit_calls = count_calls(run_dir / "fit-calls.jsonl", case["fit"]["actual_solver_calls"])
            assert case["fit"]["scipy_nfev"] <= 40
            count_calls(run_dir / "control-calls.jsonl", case["control"]["actual_solver_calls"])
            assert case["control"]["iterations"] <= 40
            assert np.isfinite(np.array([call["residual_rmse_K"] for call in actual_fit_calls])).all()
            ratios = np.array(case["fit"]["ratios"])
            assert np.all(ratios >= 0.9 / 1.1 - 1e-10) and np.all(ratios <= 1.1 / 0.9 + 1e-10)
            true_ratios = np.array([factors[name] / factors["heat_capacity"] for name in ["axial_conductance", "convection", "emissivity", "power_gain"]])
            np.testing.assert_allclose(case["true_ratios_for_scoring_only"], true_ratios, rtol=0, atol=0)
            np.testing.assert_allclose(case["ratio_relative_errors"], ratios / true_ratios - 1, rtol=0, atol=0)
            with np.load(run_dir / "fit-diagnostics.npz") as diagnostics:
                singular = np.linalg.svd(diagnostics["jacobian"], compute_uv=False)
                np.testing.assert_allclose(singular, case["fit"]["singular_values"])
                assert np.isclose(np.sqrt(np.mean(diagnostics["residuals"]**2)) * 0.1, case["fit"]["train_rmse_K"])
                with warnings.catch_warnings(record=True) as captured:
                    warnings.simplefilter("always")
                    times, fresh_prediction = sensor_prediction(ratios)
                with np.load(folder / "observations.npz") as observations:
                    fresh_residual = ((fresh_prediction - observations["noisy"][replicate]) / 0.1).ravel()
                    np.testing.assert_array_equal(times, observations["times"])
                residual_difference_K = float(np.max(abs(fresh_residual - diagnostics["residuals"])) * 0.1)
                assert residual_difference_K < 1e-6
                fit_reproductions.append({"object": object_index, "replicate": replicate,
                                          "max_residual_difference_K": residual_difference_K,
                                          "warnings": [str(item.message) for item in captured]})
            with np.load(run_dir / "heldout-predictions.npz") as predicted:
                assert predicted["truth"].shape == (721, 96)
                for name in ["nominal", "calibrated"]:
                    error = float(np.sqrt(np.mean((predicted[name] - predicted["truth"])**2)))
                    assert np.isclose(error, case["prediction"][f"{name}_rmse_K"])
            assert case["nominal_physical"] == nominal_physical
            verify_physical(run_dir / "calibrated-physical.npz", factors, case["calibrated_physical"])
            if case["refinement"] is not None:
                assert object_index in [0, 7] and replicate == 0
                refined = case["refinement"]
                verify_physical(run_dir / "refined-physical.npz", factors, refined["metrics"], samples=2881)
                assert refined["numerics_pass"]
                assert refined["classification_changed"] == (refined["metrics"]["feasible"] != case["calibrated_physical"]["feasible"])
            fit_calls += case["fit"]["actual_solver_calls"]
            control_calls += case["control"]["actual_solver_calls"]
            cases.append(case)
    assert len(cases) == summary["fit_count"] == 16
    assert fit_calls == summary["fit_solver_calls_sum"] and control_calls == summary["calibrated_control_solver_calls_sum"]
    assert sum(case["fit"]["success"] for case in cases) == summary["fit_success_count"]
    assert sum(case["control"]["success"] for case in cases) == summary["control_success_count"]
    assert sum(case["calibrated_physical"]["feasible"] for case in cases) == summary["calibrated_feasible_runs"]
    assert sum(case["nominal_physical"]["feasible"] for case in cases if case["noise_replicate"] == 0) == summary["nominal_feasible_objects"]
    assert sum(case["prediction"]["calibrated_rmse_K"] < case["prediction"]["nominal_rmse_K"] for case in cases) == summary["paired_prediction_improvements"]
    assert sum(case["calibrated_physical"]["mse_K2"] < case["nominal_physical"]["mse_K2"] for case in cases) == summary["paired_control_mse_improvements"]
    assert np.isclose(np.median([case["prediction"]["nominal_rmse_K"] for case in cases if case["noise_replicate"] == 0]), summary["nominal_heldout_rmse_median_K"])
    assert np.isclose(np.median([case["prediction"]["calibrated_rmse_K"] for case in cases]), summary["calibrated_heldout_rmse_median_K"])
    assert summary["all_refinement_checks_pass"]
    checks = {
        "status": "PASS", "objects": 8, "fits": 16, "observation_reproduction": observation_reproduction,
        "fresh_fit_prediction_checks": fit_reproductions,
        "fit_solver_calls": fit_calls, "calibrated_control_solver_calls": control_calls,
        "checks": ["frozen sources and case design", "new cases not in prior scan", "144 observations and exact noise regeneration",
                   "fit interface has no truth/validation arguments", "frozen fits and numerical budgets", "fresh fit prediction replay and warning capture", "saved residual/SVD and prediction errors",
                   "matched physical evaluation and energy balance", "input limits and sampled temperature feasibility", "two predefined refinement cases"],
    }
    (results / "verification.json").write_text(json.dumps(checks, indent=2) + "\n")
    errors = np.array([case["ratio_relative_errors"] for case in cases]) * 100
    diagnostic_summary = {
        "ratio_median_absolute_relative_error_percent": np.median(abs(errors), axis=0).tolist(),
        "ratio_max_absolute_relative_error_percent": np.max(abs(errors), axis=0).tolist(),
        "jacobian_condition_range": [min(case["fit"]["jacobian_condition"] for case in cases), max(case["fit"]["jacobian_condition"] for case in cases)],
        "convection_radiation_jacobian_cosine_range": [min(case["fit"]["jacobian_column_cosines"][1][2] for case in cases), max(case["fit"]["jacobian_column_cosines"][1][2] for case in cases)],
        "fit_train_rmse_range_K": [min(case["fit"]["train_rmse_K"] for case in cases), max(case["fit"]["train_rmse_K"] for case in cases)],
        "active_bound_fits": sum(any(case["fit"]["active_mask"]) for case in cases),
        "holdout_calibrated_rmse_range_K": [min(case["prediction"]["calibrated_rmse_K"] for case in cases), max(case["prediction"]["calibrated_rmse_K"] for case in cases)],
        "calibrated_final_mean_range_K": [min(case["calibrated_physical"]["final_mean_K"] for case in cases), max(case["calibrated_physical"]["final_mean_K"] for case in cases)],
        "calibrated_peak_K": max(case["calibrated_physical"]["peak_K"] for case in cases),
        "calibrated_max_spread_K": max(case["calibrated_physical"]["max_spread_K"] for case in cases),
        "refinement_sensor_max_K": max(case["refinement"]["calibration_sensor_grid_difference_K"] for case in cases if case["refinement"]),
        "refinement_temperature_max_K": max(abs(case["refinement"]["metric_changes"][key]) for case in cases if case["refinement"] for key in ["peak_K", "max_spread_K", "final_mean_K"]),
    }
    (results / "diagnostic-summary.json").write_text(json.dumps(diagnostic_summary, indent=2) + "\n")
    for check in checks["checks"]:
        print("PASS", check)
    print("NOT CLAIMED: absolute parameter identification, real sensor accuracy, independent model validation or industrial reliability")


if __name__ == "__main__":
    main()
