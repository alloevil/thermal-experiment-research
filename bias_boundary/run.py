import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "model_mismatch"))

from experiment import (
    CALIBRATION_KNOTS, CALIBRATION_POWERS, DIAGNOSTIC_KNOTS, DIAGNOSTIC_POWERS,
    FACTOR_NAMES, EffectiveModel, fit_ratios, np, physical, prediction_score,
    residual_alarm, sensor_values, write_json,
)
from scipy.stats import qmc

BIASES = [-.4, -.3, -.2, 0, .2, .3, .4]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identify(index, replicate, bias):
    return f"object-{index}-noise-{replicate}-bias-{bias:+.1f}"


def read_json(path):
    return json.loads(path.read_text())


def candidates_for_refinement(cases):
    chosen = set()
    for bias in BIASES:
        subset = [case for case in cases if case["bias_K"] == bias]
        chosen.add(min(subset, key=lambda case: (abs(case["score"]["rmse_K"] - .5), case["id"]))["id"])
    chosen.update(case["id"] for case in cases if case["score"]["inadequate"] and not case["alarm"]["combined"])
    return sorted(chosen)


def run():
    started = time.perf_counter()
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    objects = [dict(zip(FACTOR_NAMES, row.tolist(), strict=True)) for row in
               .9 + .2 * qmc.Sobol(5, scramble=True, seed=20260927).random_base2(1)]
    files = {"protocol.md": ROOT / "protocol.md", "run.py": Path(__file__),
             "model_mismatch/experiment.py": ROOT.parent / "model_mismatch/experiment.py",
             "calibration/effective.py": ROOT.parent / "calibration/effective.py",
             "calibration/fit_and_control.py": ROOT.parent / "calibration/fit_and_control.py",
             "radiation/model.py": ROOT.parent / "radiation/model.py",
             "radiation/results/experiment.json": ROOT.parent / "radiation/results/experiment.json",
             "feasibility/requirements.lock": ROOT.parent / "feasibility/requirements.lock"}
    process = np.array(read_json(files["radiation/results/experiment.json"])["optimized_powers_W"])
    config = {"hashes": {name: digest(path) for name, path in files.items()}, "objects": objects,
              "biases_K": BIASES, "replicates": 2, "process_powers": process.tolist()}
    if (results / "config.json").exists():
        assert read_json(results / "config.json") == config, "Changed configuration; archive results before rerunning"
    else:
        write_json(results / "config.json", config)
    if (results / "summary.json").exists():
        print("Completed; use verify.py")
        return
    cases = []
    for index, factors in enumerate(objects):
        shared = results / f"object-{index}"
        shared.mkdir(exist_ok=True)
        for name, powers, knots, step in [
            ("training", CALIBRATION_POWERS, CALIBRATION_KNOTS, 5),
            ("diagnostic", DIAGNOSTIC_POWERS, DIAGNOSTIC_KNOTS, 5),
            ("truth", process, [0, 60, 120, 180], .25),
        ]:
            if not (shared / f"{name}.npz").exists():
                model, output, energy = physical(factors, "clean", powers, knots, step=step)
                np.savez_compressed(shared / f"{name}.npz", **output, sensors=sensor_values(model, output))
                write_json(shared / f"{name}-energy.json", energy)
        with np.load(shared / "training.npz") as data:
            times, clean_train = data["time"][1:], data["sensors"][1:]
        with np.load(shared / "diagnostic.npz") as data:
            clean_diagnostic = data["sensors"][1:]
        for replicate in range(2):
            train_noise = np.random.default_rng(20260927 + 100 * index + 10 * replicate).normal(0, .1, (48, 3))
            diag_noise = np.random.default_rng(20260928 + 100 * index + 10 * replicate).normal(0, .1, (48, 3))
            for bias in BIASES:
                case_id = identify(index, replicate, bias)
                folder = results / case_id
                folder.mkdir(exist_ok=True)
                if (folder / "case.json").exists():
                    cases.append(read_json(folder / "case.json"))
                    continue
                observed = clean_train + bias + train_noise
                diagnostic = clean_diagnostic + bias + diag_noise
                fit = fit_ratios(times, observed, folder)
                fit_hash = digest(folder / "fit.json")
                model = EffectiveModel(fit["ratios"], cells=48)
                train_result = model.solve(CALIBRATION_POWERS, knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-9, atol=1e-10)
                diag_result = model.solve(DIAGNOSTIC_POWERS, knots=DIAGNOSTIC_KNOTS, sample_step=5, rtol=1e-9, atol=1e-10)
                train_prediction = sensor_values(model, train_result)[1:]
                diag_prediction = sensor_values(model, diag_result)[1:]
                training_alarm = residual_alarm(train_prediction - observed, fit["success"])
                diagnostic_alarm = residual_alarm(diag_prediction - diagnostic)
                alarm = {"training": training_alarm, "diagnostic": diagnostic_alarm,
                         "combined": training_alarm["alarm"] or diagnostic_alarm["alarm"]}
                write_json(folder / "alarm.json", alarm)
                alarm_hash = digest(folder / "alarm.json")
                np.savez_compressed(folder / "observations.npz", time=times, training=observed, diagnostic=diagnostic,
                                    training_noise=train_noise, diagnostic_noise=diag_noise,
                                    training_prediction=train_prediction, diagnostic_prediction=diag_prediction)
                output = EffectiveModel(fit["ratios"], cells=96).solve(process, sample_step=.25, rtol=1e-10, atol=1e-11)
                with np.load(shared / "truth.npz") as data:
                    score = prediction_score(data["temperature"], output["temperature"])
                np.savez_compressed(folder / "prediction.npz", time=output["time"], temperature=output["temperature"])
                assert digest(folder / "fit.json") == fit_hash and digest(folder / "alarm.json") == alarm_hash
                case = {"id": case_id, "object": index, "noise": replicate, "bias_K": bias, "fit": fit,
                        "fit_hash": fit_hash, "alarm_hash": alarm_hash, "alarm": alarm, "score": score,
                        "near_boundary": abs(score["rmse_K"] - .5) <= .02 or any(abs(item["rmse_K"] - .2) <= .02
                                                                                  for item in [training_alarm, diagnostic_alarm])}
                write_json(folder / "case.json", case)
                cases.append(case)
                print(f"CASE {case_id}: residual={training_alarm['rmse_K']:.4f}/{diagnostic_alarm['rmse_K']:.4f}K hidden={score['rmse_K']:.4f}K alarm={alarm['combined']} inadequate={score['inadequate']}", flush=True)
    selected = candidates_for_refinement(cases)
    write_json(results / "refinement-selection.json", selected)
    for case_id in selected:
        case = next(item for item in cases if item["id"] == case_id)
        folder = results / case_id
        if (folder / "refinement.json").exists():
            continue
        _, truth, energy = physical(objects[case["object"]], "clean", process, [0, 60, 120, 180], cells=192, step=.0625)
        output = EffectiveModel(case["fit"]["ratios"], cells=192).solve(process, sample_step=.0625, rtol=1e-10, atol=1e-11)
        fine_score = prediction_score(truth["temperature"], output["temperature"])
        changes = {name: fine_score[name] - case["score"][name] for name in ["rmse_K", "final_mean_error_K"]}
        assert max(abs(value) for value in changes.values()) < .01
        refinement = {"score": fine_score, "changes": changes, "energy": energy,
                      "label_flipped": fine_score["inadequate"] != case["score"]["inadequate"]}
        if case["score"]["inadequate"] and not case["alarm"]["combined"]:
            model = EffectiveModel(case["fit"]["ratios"], cells=96)
            training = model.solve(CALIBRATION_POWERS, knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-10, atol=1e-11)
            diagnostic = model.solve(DIAGNOSTIC_POWERS, knots=DIAGNOSTIC_KNOTS, sample_step=5, rtol=1e-10, atol=1e-11)
            with np.load(folder / "observations.npz") as data:
                train_residual = sensor_values(model, training)[1:] - data["training"]
                diag_residual = sensor_values(model, diagnostic)[1:] - data["diagnostic"]
            train_alarm = residual_alarm(train_residual, case["fit"]["success"])
            diag_alarm = residual_alarm(diag_residual)
            refinement["alarm96"] = {"training": train_alarm, "diagnostic": diag_alarm,
                                      "combined": train_alarm["alarm"] or diag_alarm["alarm"]}
            np.savez_compressed(folder / "alarm96.npz", train_residual=train_residual, diagnostic_residual=diag_residual)
        np.savez_compressed(folder / "refined.npz", time=truth["time"], truth=truth["temperature"], prediction=output["temperature"])
        write_json(folder / "refinement.json", refinement)
        print(f"REFINED {case_id} change={changes} flipped={refinement['label_flipped']}", flush=True)
    groups = {}
    for bias in BIASES:
        subset = [case for case in cases if case["bias_K"] == bias]
        group = {"count": len(subset), "inadequate": sum(case["score"]["inadequate"] for case in subset)}
        for rule in ["training", "combined"]:
            counts = dict.fromkeys(["TP", "FP", "FN", "TN"], 0)
            for case in subset:
                alarm = case["alarm"]["training"]["alarm"] if rule == "training" else case["alarm"]["combined"]
                truth = case["score"]["inadequate"]
                counts["TP" if alarm and truth else "FP" if alarm else "FN" if truth else "TN"] += 1
            group[rule] = counts
        groups[str(bias)] = group
    summary = {"status": "COMPLETED", "cases": len(cases), "fit_success": sum(case["fit"]["success"] for case in cases),
               "groups": groups, "combined_misses": [case["id"] for case in cases if case["score"]["inadequate"] and not case["alarm"]["combined"]],
               "near_boundary": [case["id"] for case in cases if case["near_boundary"]],
               "refinements": selected, "fit_calls": sum(case["fit"]["actual_solver_calls"] for case in cases),
               "fit_seconds": sum(case["fit"]["wall_seconds"] for case in cases), "invocation_wall_seconds": time.perf_counter() - started}
    write_json(results / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    run()
