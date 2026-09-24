import hashlib
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

from effective import (
    CALIBRATION_KNOTS, CALIBRATION_POWERS, SENSOR_POSITIONS, RATIO_NAMES,
    EffectiveModel, HeatingModel, Parameters, input_feasible, metrics, np, sensor_prediction,
    sensor_values, temperature_margins,
)
from fit_and_control import fit_ratios, optimize_control, write_json
from scipy.stats import qmc


ROOT = Path(__file__).resolve().parent
FACTOR_NAMES = ["emissivity", "convection", "heat_capacity", "power_gain", "axial_conductance"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_physical_model(factors, cells=96):
    params = Parameters()
    return HeatingModel(cells, parameters=replace(params, **{
        name: getattr(params, name) * value for name, value in factors.items() if name != "power_gain"
    }))


def physical_assessment(factors, powers, path, refined=False):
    model = make_physical_model(factors, cells=192 if refined else 96)
    powers = np.array(powers)
    actual_powers = powers * factors["power_gain"]
    result = model.solve(actual_powers, sample_step=0.0625 if refined else 0.25,
                         rtol=1e-11 if refined else 1e-10, atol=1e-12 if refined else 1e-11)
    summary = metrics(model, result)
    convection, radiation = model.losses(result["temperature"])
    exact_absorbed = float(np.trapezoid(actual_powers.sum(axis=1), [0, 60, 120, 180]))
    balance = exact_absorbed - np.trapezoid(convection.sum(axis=1) + radiation.sum(axis=1), result["time"]) - summary["stored_J"]
    assert summary["max_balance_residual_J"] < 1e-4
    assert abs(exact_absorbed - summary["absorbed_J"]) < 1e-4 and abs(balance) < 0.1
    summary["margins_K"] = temperature_margins(summary).tolist()
    summary["command_feasible"] = input_feasible(powers)
    summary["actual_power_feasible"] = input_feasible(powers, factors["power_gain"])
    summary["feasible"] = bool(min(summary["margins_K"]) >= -1e-5 and summary["command_feasible"] and summary["actual_power_feasible"])
    summary["external_energy_balance_J"] = float(balance)
    np.savez_compressed(path, **result, command_powers=powers, actual_powers=actual_powers,
                        convection=convection.sum(axis=1), radiation=radiation.sum(axis=1))
    return result, summary


def main():
    started = time.perf_counter()
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    initial_powers = json.loads((ROOT.parent / "radiation/results/experiment.json").read_text())["optimized_powers_W"]
    factors_table = 0.9 + 0.2 * qmc.Sobol(5, scramble=True, seed=20260925).random_base2(3)
    objects = [dict(zip(FACTOR_NAMES, row.tolist(), strict=True)) for row in factors_table]
    dependencies = {
        "protocol.md": ROOT / "protocol.md", "effective.py": ROOT / "effective.py",
        "fit_and_control.py": ROOT / "fit_and_control.py", "run_experiment.py": Path(__file__),
        "radiation/model.py": ROOT.parent / "radiation/model.py",
        "radiation/results/experiment.json": ROOT.parent / "radiation/results/experiment.json",
        "feasibility/requirements.lock": ROOT.parent / "feasibility/requirements.lock",
    }
    config = {"objects": objects, "hashes": {name: digest(path) for name, path in dependencies.items()},
              "calibration_knots": CALIBRATION_KNOTS.tolist(), "calibration_commands": CALIBRATION_POWERS.tolist(),
              "sensor_positions_m": SENSOR_POSITIONS.tolist(), "noise_std_K": 0.1, "initial_powers": initial_powers,
              "ratio_names": RATIO_NAMES, "ratio_bounds": [0.9 / 1.1, 1.1 / 0.9], "replicates": 2}
    if (results / "config.json").exists():
        assert json.loads((results / "config.json").read_text()) == config, "Configuration changed; archive before restarting"
    else:
        write_json(results / "config.json", config)
    assert json.loads((results / "model-checks.json").read_text())["status"] == "PASS"
    if (results / "summary.json").exists():
        print("Completed experiment exists; run verify_results.py, not a fresh optimization")
        return
    nominal_control = optimize_control(np.ones(4), initial_powers, results / "nominal-control")
    print(f"NOMINAL CONTROL success={nominal_control['success']} time={nominal_control['wall_seconds']:.2f}s", flush=True)
    completed = []
    for object_index, factors in enumerate(objects):
        folder = results / f"object-{object_index}"
        folder.mkdir(exist_ok=True)
        observations_path = folder / "observations.npz"
        if not observations_path.exists():
            physical_model = make_physical_model(factors)
            calibration_result = physical_model.solve(CALIBRATION_POWERS * factors["power_gain"], knots=CALIBRATION_KNOTS,
                                                       sample_step=5, rtol=1e-10, atol=1e-11)
            clean = sensor_values(physical_model, calibration_result)[1:]
            observed = np.stack([clean + np.random.default_rng(20260925 + 100 * object_index + replicate).normal(0, 0.1, clean.shape)
                                 for replicate in range(2)])
            np.savez_compressed(observations_path, times=calibration_result["time"][1:], noisy=observed, clean=clean)
        with np.load(observations_path) as data:
            observed_times, noisy = data["times"].copy(), data["noisy"].copy()
        for replicate in range(2):
            run_dir = folder / f"noise-{replicate}"
            run_dir.mkdir(exist_ok=True)
            if (run_dir / "case.json").exists():
                completed.append(json.loads((run_dir / "case.json").read_text()))
                continue
            fit = fit_ratios(observed_times, noisy[replicate], run_dir)
            fit_hash = digest(run_dir / "fit.json")
            ratios = np.array(fit["ratios"])
            print(f"FIT object={object_index} noise={replicate} success={fit['success']} train={fit['train_rmse_K']:.4f}K cond={fit['jacobian_condition']:.1f}", flush=True)
            if not (folder / "nominal-physical.json").exists():
                _, nominal_metrics = physical_assessment(factors, nominal_control["powers"], folder / "nominal-physical.npz")
                write_json(folder / "nominal-physical.json", nominal_metrics)
            nominal_metrics = json.loads((folder / "nominal-physical.json").read_text())
            physical_model = make_physical_model(factors)
            heldout_truth = physical_model.solve(np.array(initial_powers) * factors["power_gain"], sample_step=0.25, rtol=1e-10, atol=1e-11)
            heldout_nominal = EffectiveModel(np.ones(4), cells=96).solve(initial_powers, sample_step=0.25, rtol=1e-10, atol=1e-11)
            heldout_calibrated = EffectiveModel(ratios, cells=96).solve(initial_powers, sample_step=0.25, rtol=1e-10, atol=1e-11)
            prediction_scores = {
                "nominal_rmse_K": float(np.sqrt(np.mean((heldout_nominal["temperature"] - heldout_truth["temperature"])**2))),
                "calibrated_rmse_K": float(np.sqrt(np.mean((heldout_calibrated["temperature"] - heldout_truth["temperature"])**2))),
            }
            np.savez_compressed(run_dir / "heldout-predictions.npz", time=heldout_truth["time"], truth=heldout_truth["temperature"],
                                nominal=heldout_nominal["temperature"], calibrated=heldout_calibrated["temperature"])
            control = optimize_control(ratios, initial_powers, run_dir)
            _, calibrated_metrics = physical_assessment(factors, control["powers"], run_dir / "calibrated-physical.npz")
            true_ratios = np.array([factors[name] / factors["heat_capacity"] for name in ["axial_conductance", "convection", "emissivity", "power_gain"]])
            refinement = None
            if object_index in [0, 7] and replicate == 0:
                _, coarse_sensors = sensor_prediction(ratios, cells=48)
                _, fine_sensors = sensor_prediction(ratios, cells=96)
                sensor_difference = float(np.max(abs(coarse_sensors - fine_sensors)))
                _, fine_metrics = physical_assessment(factors, control["powers"], run_dir / "refined-physical.npz", refined=True)
                changes = {name: fine_metrics[name] - calibrated_metrics[name] for name in ["peak_K", "max_spread_K", "final_mean_K", "mse_K2"]}
                refinement = {"calibration_sensor_grid_difference_K": sensor_difference, "metrics": fine_metrics,
                              "metric_changes": changes, "classification_changed": fine_metrics["feasible"] != calibrated_metrics["feasible"],
                              "numerics_pass": sensor_difference < 0.02 and all(abs(changes[name]) < 0.01 for name in ["peak_K", "max_spread_K", "final_mean_K"])}
            assert digest(run_dir / "fit.json") == fit_hash
            case = {"object": object_index, "noise_replicate": replicate, "fit": fit, "fit_frozen_sha256": fit_hash,
                    "true_ratios_for_scoring_only": true_ratios.tolist(), "ratio_relative_errors": (ratios / true_ratios - 1).tolist(),
                    "prediction": prediction_scores, "control": control, "nominal_physical": nominal_metrics,
                    "calibrated_physical": calibrated_metrics, "refinement": refinement}
            write_json(run_dir / "case.json", case)
            completed.append(case)
            print(f"RESULT {object_index}/{replicate}: heldout {prediction_scores['nominal_rmse_K']:.4f}->{prediction_scores['calibrated_rmse_K']:.4f}K feasible {nominal_metrics['feasible']}->{calibrated_metrics['feasible']}", flush=True)
    summary = {
        "status": "COMPLETED", "object_count": 8, "fit_count": len(completed),
        "fit_success_count": sum(case["fit"]["success"] for case in completed),
        "control_success_count": sum(case["control"]["success"] for case in completed),
        "nominal_control_success": nominal_control["success"],
        "nominal_feasible_objects": sum(case["nominal_physical"]["feasible"] for case in completed if case["noise_replicate"] == 0),
        "calibrated_feasible_runs": sum(case["calibrated_physical"]["feasible"] for case in completed),
        "nominal_heldout_rmse_median_K": float(np.median([case["prediction"]["nominal_rmse_K"] for case in completed if case["noise_replicate"] == 0])),
        "calibrated_heldout_rmse_median_K": float(np.median([case["prediction"]["calibrated_rmse_K"] for case in completed])),
        "paired_prediction_improvements": sum(case["prediction"]["calibrated_rmse_K"] < case["prediction"]["nominal_rmse_K"] for case in completed),
        "paired_control_mse_improvements": sum(case["calibrated_physical"]["mse_K2"] < case["nominal_physical"]["mse_K2"] for case in completed),
        "fit_wall_seconds_sum": sum(case["fit"]["wall_seconds"] for case in completed),
        "fit_solver_calls_sum": sum(case["fit"]["actual_solver_calls"] for case in completed),
        "calibrated_control_wall_seconds_sum": sum(case["control"]["wall_seconds"] for case in completed),
        "calibrated_control_solver_calls_sum": sum(case["control"]["actual_solver_calls"] for case in completed),
        "nominal_control": nominal_control, "invocation_wall_seconds": time.perf_counter() - started,
        "all_refinement_checks_pass": all(case["refinement"]["numerics_pass"] for case in completed if case["refinement"] is not None),
        "refinement_classification_flips": [f"{case['object']}/{case['noise_replicate']}" for case in completed
                                            if case["refinement"] is not None and case["refinement"]["classification_changed"]],
    }
    write_json(results / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
