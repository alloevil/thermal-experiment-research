import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "calibration"))

from effective import CALIBRATION_KNOTS, CALIBRATION_POWERS, EffectiveModel, HeatingModel, Parameters, np, sensor_values
from fit_and_control import fit_ratios, write_json
from scipy.stats import qmc

SCENARIOS = ["clean", "bias", "lag", "cooling"]
FACTOR_NAMES = ["emissivity", "convection", "heat_capacity", "power_gain", "axial_conductance"]
DIAGNOSTIC_KNOTS = np.arange(0, 241, 30, dtype=float)
DIAGNOSTIC_POWERS = np.array([[0, 0, 0], [.25, .25, .25], [.25, .25, .25], [.5, .15, .15],
                              [.15, .5, .15], [.15, .15, .5], [.3, .3, .3], [.1, .1, .1], [0, 0, 0]])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lag_filter(times, temperatures, tau=8.0):
    filtered = np.empty_like(temperatures)
    filtered[0] = temperatures[0]
    for index in range(1, len(times)):
        duration = times[index] - times[index - 1]
        one_minus_decay = -np.expm1(-duration / tau)
        slope = (temperatures[index] - temperatures[index - 1]) / duration
        filtered[index] = (filtered[index - 1] * (1 - one_minus_decay)
                           + temperatures[index - 1] * one_minus_decay
                           + slope * (duration - tau * one_minus_decay))
    return filtered


def check_lag():
    times = np.linspace(0, 100, 401)
    constant = np.full((len(times), 3), 296.15)
    constant_error = float(np.max(abs(lag_filter(times, constant) - constant)))
    slope = np.array([.1, .2, .3])
    ramp = constant + times[:, None] * slope
    exact = constant + (times - 8 * (1 - np.exp(-times / 8)))[:, None] * slope
    ramp_error = float(np.max(abs(lag_filter(times, ramp) - exact)))
    assert max(constant_error, ramp_error) < 1e-9
    return {"status": "PASS", "constant_error_K": constant_error, "ramp_error_K": ramp_error}


def residual_alarm(residual, fit_success=True):
    rmse = float(np.sqrt(np.mean(residual**2)))
    mean_bias = float(np.max(abs(np.mean(residual, axis=0))))
    reasons = []
    if not fit_success:
        reasons.append("fit_not_converged")
    if rmse > .2:
        reasons.append("residual_rmse_above_0.2K")
    if mean_bias > .2:
        reasons.append("sensor_mean_residual_above_0.2K")
    return {"alarm": bool(reasons), "reasons": reasons, "rmse_K": rmse, "max_sensor_mean_residual_K": mean_bias}


def prediction_score(truth, prediction):
    rmse = float(np.sqrt(np.mean((truth - prediction)**2)))
    final_error = float(abs(truth[-1].mean() - prediction[-1].mean()))
    return {"rmse_K": rmse, "final_mean_error_K": final_error,
            "inadequate": rmse > .5 or final_error > 1}


def physical(factors, scenario, powers, knots, cells=96, step=.25):
    nominal = Parameters()
    params = replace(nominal, **{name: getattr(nominal, name) * factor for name, factor in factors.items() if name != "power_gain"},
                     convection_variation=.6 if scenario == "cooling" else .3)
    model = HeatingModel(cells, parameters=params)
    actual = np.asarray(powers) * factors["power_gain"]
    assert actual.min() >= 0 and actual.max() <= 1
    assert np.max(abs(np.diff(actual, axis=0) / np.diff(knots)[:, None])) <= .015 + 1e-9
    result = model.solve(actual, knots=knots, sample_step=step, rtol=1e-10, atol=1e-11)
    stored = model.cell_capacity * np.sum(result["temperature"] - params.ambient, axis=1)
    ledger = result["ledger"]
    balance = float(np.max(abs(stored - ledger[:, 0] + ledger[:, 1] + ledger[:, 2])))
    absorbed = float(np.trapezoid(actual.sum(axis=1), knots))
    convective, radiative = model.losses(result["temperature"])
    external_balance = float(absorbed - np.trapezoid((convective + radiative).sum(axis=1), result["time"]) - stored[-1])
    assert balance < 1e-4 and abs(absorbed - ledger[-1, 0]) < 1e-4 and abs(external_balance) < .1
    return model, result, {"max_balance_J": balance, "external_balance_J": external_balance,
                           "absorbed_J": absorbed, "wall_seconds": result["wall_seconds"]}


def observations(factors, scenario, powers, knots, noise, step=.25):
    model, result, energy = physical(factors, scenario, powers, knots, step=step)
    ideal = sensor_values(model, result)
    distorted = lag_filter(result["time"], ideal) if scenario == "lag" else ideal + (.5 if scenario == "bias" else 0)
    sampled_times = np.arange(5, 241, 5)
    sampled = np.array([np.interp(sampled_times, result["time"], distorted[:, sensor]) for sensor in range(3)]).T
    return sampled_times, sampled + noise, sampled, energy


def main():
    started = time.perf_counter()
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    objects = [dict(zip(FACTOR_NAMES, values.tolist(), strict=True)) for values in
               .9 + .2 * qmc.Sobol(5, scramble=True, seed=20260926).random_base2(2)]
    files = {"protocol.md": ROOT / "protocol.md", "experiment.py": Path(__file__),
             "radiation/model.py": ROOT.parent / "radiation/model.py",
             "calibration/effective.py": ROOT.parent / "calibration/effective.py",
             "calibration/fit_and_control.py": ROOT.parent / "calibration/fit_and_control.py",
             "radiation/results/experiment.json": ROOT.parent / "radiation/results/experiment.json",
             "feasibility/requirements.lock": ROOT.parent / "feasibility/requirements.lock"}
    process_powers = np.array(json.loads(files["radiation/results/experiment.json"].read_text())["optimized_powers_W"])
    config = {"objects": objects, "scenarios": SCENARIOS, "hashes": {name: digest(path) for name, path in files.items()},
              "diagnostic_knots": DIAGNOSTIC_KNOTS.tolist(), "diagnostic_powers": DIAGNOSTIC_POWERS.tolist(),
              "process_powers": process_powers.tolist()}
    if (results / "config.json").exists():
        assert json.loads((results / "config.json").read_text()) == config, "Changed config; archive before rerunning"
    else:
        write_json(results / "config.json", config)
    if (results / "summary.json").exists():
        print("Complete results exist; use verify.py")
        return
    write_json(results / "lag-check.json", check_lag())
    cases = []
    for index, factors in enumerate(objects):
        train_noise = np.random.default_rng(20260926 + 100 * index).normal(0, .1, (48, 3))
        diagnostic_noise = np.random.default_rng(20260927 + 100 * index).normal(0, .1, (48, 3))
        for scenario in SCENARIOS:
            folder = results / f"object-{index}-{scenario}"
            folder.mkdir(exist_ok=True)
            if (folder / "case.json").exists():
                cases.append(json.loads((folder / "case.json").read_text()))
                continue
            if not (folder / "training.npz").exists():
                times, noisy, distorted, energy = observations(factors, scenario, CALIBRATION_POWERS, CALIBRATION_KNOTS, train_noise)
                np.savez_compressed(folder / "training.npz", time=times, noisy=noisy, distorted=distorted, noise=train_noise)
                write_json(folder / "training-energy.json", energy)
            with np.load(folder / "training.npz") as data:
                times, noisy = data["time"].copy(), data["noisy"].copy()
            fit = fit_ratios(times, noisy, folder)
            frozen_hash = digest(folder / "fit.json")
            model = EffectiveModel(fit["ratios"], cells=48)
            fitted = model.solve(CALIBRATION_POWERS, knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-9, atol=1e-10)
            train_residual = sensor_values(model, fitted)[1:] - noisy
            training_alarm = residual_alarm(train_residual, fit["success"])
            diagnostic_times, measured, distorted, diagnostic_energy = observations(factors, scenario, DIAGNOSTIC_POWERS, DIAGNOSTIC_KNOTS, diagnostic_noise)
            predicted = model.solve(DIAGNOSTIC_POWERS, knots=DIAGNOSTIC_KNOTS, sample_step=5, rtol=1e-9, atol=1e-10)
            diagnostic_residual = sensor_values(model, predicted)[1:] - measured
            diagnostic_alarm = residual_alarm(diagnostic_residual)
            np.savez_compressed(folder / "diagnostic.npz", time=diagnostic_times, measured=measured, distorted=distorted,
                                noise=diagnostic_noise, predicted=sensor_values(model, predicted)[1:])
            np.savez_compressed(folder / "train-prediction.npz", predicted=sensor_values(model, fitted)[1:])
            alarm_decision = {"training": training_alarm, "diagnostic": diagnostic_alarm,
                              "combined_alarm": training_alarm["alarm"] or diagnostic_alarm["alarm"]}
            write_json(folder / "alarm.json", alarm_decision)
            frozen_alarm_hash = digest(folder / "alarm.json")
            _, truth, energy = physical(factors, scenario, process_powers, [0, 60, 120, 180])
            prediction = EffectiveModel(fit["ratios"], cells=96).solve(process_powers, sample_step=.25, rtol=1e-10, atol=1e-11)
            score = prediction_score(truth["temperature"], prediction["temperature"])
            np.savez_compressed(folder / "evaluation.npz", time=truth["time"], truth=truth["temperature"], prediction=prediction["temperature"])
            refinement = None
            if index == 0:
                _, fine_truth, fine_energy = physical(factors, scenario, process_powers, [0, 60, 120, 180], cells=192, step=.0625)
                fine_prediction = EffectiveModel(fit["ratios"], cells=192).solve(process_powers, sample_step=.0625, rtol=1e-10, atol=1e-11)
                fine_score = prediction_score(fine_truth["temperature"], fine_prediction["temperature"])
                refinement = {"score": fine_score, "energy": fine_energy, "classification_changed": fine_score["inadequate"] != score["inadequate"],
                              "differences": {name: fine_score[name] - score[name] for name in ["rmse_K", "final_mean_error_K"]}}
                assert max(abs(value) for value in refinement["differences"].values()) < .01
                if scenario == "lag":
                    _, _, fine_sensors, _ = observations(factors, scenario, CALIBRATION_POWERS, CALIBRATION_KNOTS, np.zeros((48, 3)), step=.0625)
                    with np.load(folder / "training.npz") as data:
                        refinement["lag_input_step_difference_K"] = float(np.max(abs(fine_sensors - data["distorted"])))
                    assert refinement["lag_input_step_difference_K"] < .001
            assert digest(folder / "fit.json") == frozen_hash and digest(folder / "alarm.json") == frozen_alarm_hash
            case = {"object": index, "scenario": scenario, "fit": fit, "fit_frozen_sha256": frozen_hash,
                    "alarm_frozen_sha256": frozen_alarm_hash, "alarm": alarm_decision, "score": score,
                    "training_energy": json.loads((folder / "training-energy.json").read_text()),
                    "diagnostic_energy": diagnostic_energy, "evaluation_energy": energy, "refinement": refinement}
            write_json(folder / "case.json", case)
            cases.append(case)
            print(f"CASE {index}/{scenario}: fit={training_alarm['rmse_K']:.4f}K diag={diagnostic_alarm['rmse_K']:.4f}K alarms={training_alarm['alarm']}/{alarm_decision['combined_alarm']} hidden_RMSE={score['rmse_K']:.4f}K inadequate={score['inadequate']}", flush=True)
    groups = {}
    for scenario in SCENARIOS:
        subset = [case for case in cases if case["scenario"] == scenario]
        groups[scenario] = {"count": len(subset), "fit_success": sum(case["fit"]["success"] for case in subset),
                            "training_alarms": sum(case["alarm"]["training"]["alarm"] for case in subset),
                            "combined_alarms": sum(case["alarm"]["combined_alarm"] for case in subset),
                            "inadequate_predictions": sum(case["score"]["inadequate"] for case in subset),
                            "hidden_rmse_range_K": [min(case["score"]["rmse_K"] for case in subset), max(case["score"]["rmse_K"] for case in subset)]}
    confusion = {}
    for rule in ["training", "combined"]:
        counts = dict.fromkeys(["TP", "FP", "FN", "TN"], 0)
        for case in cases:
            alarm = case["alarm"]["training"]["alarm"] if rule == "training" else case["alarm"]["combined_alarm"]
            counts[("T" if alarm == case["score"]["inadequate"] else "F") + ("P" if alarm else "N")] += 1
        confusion[rule] = counts
    write_json(results / "summary.json", {"status": "COMPLETED", "groups": groups, "confusion_vs_hidden_prediction": confusion,
                                          "fit_calls": sum(case["fit"]["actual_solver_calls"] for case in cases),
                                          "fit_seconds": sum(case["fit"]["wall_seconds"] for case in cases),
                                          "invocation_wall_seconds": time.perf_counter() - started})
    print(json.dumps(json.loads((results / "summary.json").read_text()), indent=2), flush=True)


if __name__ == "__main__":
    main()
