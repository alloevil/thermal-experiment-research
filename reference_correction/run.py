import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "model_mismatch"))

from experiment import (CALIBRATION_KNOTS, CALIBRATION_POWERS, DIAGNOSTIC_KNOTS, DIAGNOSTIC_POWERS,
                        FACTOR_NAMES, EffectiveModel, fit_ratios, physical, prediction_score,
                        residual_alarm, sensor_values, write_json, np)
from correction import estimate_offset, apply_offset
from scipy.stats import qmc

SCENARIOS = ["clean", "stable", "reference_bias", "thermal_drift"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def branch_key(index, replicate, scenario, branch):
    return f"object-{index}/noise-{replicate}-{scenario}/{branch}"


def refinement_keys(cases):
    return sorted({case["key"] for case in cases if case["branch"] == "corrected" and (
        (case["object"] == 0 and case["replicate"] == 0) or
        (case["score"]["inadequate"] and not case["alarm"]["combined"]))})


def main():
    start = time.perf_counter()
    results = ROOT / "results"
    assert load(results / "correction-checks.json")["status"] == "PASS"
    objects = [dict(zip(FACTOR_NAMES, row.tolist(), strict=True)) for row in
               .9 + .2 * qmc.Sobol(5, scramble=True, seed=20260928).random_base2(1)]
    source_names = ["protocol.md", "run.py", "correction.py", "model_mismatch/experiment.py",
                    "calibration/effective.py", "calibration/fit_and_control.py", "radiation/model.py",
                    "radiation/results/experiment.json", "feasibility/requirements.lock"]
    hashes = {name: digest(ROOT / name if "/" not in name else ROOT.parent / name) for name in source_names}
    process = np.array(load(ROOT.parent / "radiation/results/experiment.json")["optimized_powers_W"])
    config = {"objects": objects, "scenarios": SCENARIOS, "replicates": 2, "hashes": hashes,
              "process_powers": process.tolist(), "anchor_samples": 10}
    if (results / "config.json").exists():
        assert config == load(results / "config.json"), "Changed configuration; archive before restarting"
    else:
        write_json(results / "config.json", config)
    if (results / "summary.json").exists():
        print("Complete; use verify.py")
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
            times, clean_training = data["time"][1:], data["sensors"][1:]
        with np.load(shared / "diagnostic.npz") as data:
            clean_diagnostic = data["sensors"][1:]
        for replicate in range(2):
            seed = 20260928 + 100 * index + 10 * replicate
            anchor_noise = np.random.default_rng(seed).normal(0, .1, (10, 3))
            reference_noise = np.random.default_rng(seed + 1).normal(0, .05, 10)
            training_noise = np.random.default_rng(seed + 2).normal(0, .1, (48, 3))
            diagnostic_noise = np.random.default_rng(seed + 3).normal(0, .1, (48, 3))
            for scenario in SCENARIOS:
                folder = shared / f"noise-{replicate}-{scenario}"
                folder.mkdir(exist_ok=True)
                bias = 0 if scenario == "clean" else (.4 if index == 0 else -.4)
                reference_bias = .35 if scenario == "reference_bias" else 0
                anchor = 296.15 + bias + anchor_noise
                reference = 296.15 + reference_bias + reference_noise
                estimate = estimate_offset(anchor, reference)
                offset_hash = None
                if (folder / "offset.json").exists():
                    assert load(folder / "offset.json") == estimate
                else:
                    write_json(folder / "offset.json", estimate)
                offset_hash = digest(folder / "offset.json")
                training_drift = .008 * (clean_training - 296.15) if scenario == "thermal_drift" else 0
                diagnostic_drift = .008 * (clean_diagnostic - 296.15) if scenario == "thermal_drift" else 0
                raw_train = clean_training + bias + training_drift + training_noise
                raw_diag = clean_diagnostic + bias + diagnostic_drift + diagnostic_noise
                corrected_train = apply_offset(raw_train, estimate["offset_K"])
                corrected_diag = apply_offset(raw_diag, estimate["offset_K"])
                np.savez_compressed(folder / "readings.npz", anchor=anchor, reference=reference,
                                    raw_train=raw_train, raw_diag=raw_diag,
                                    corrected_train=corrected_train, corrected_diag=corrected_diag,
                                    time=times)
                for branch in ["raw", "corrected"]:
                    output_dir = folder / branch
                    output_dir.mkdir(exist_ok=True)
                    if (output_dir / "case.json").exists():
                        cases.append(load(output_dir / "case.json"))
                        continue
                    observed = raw_train if branch == "raw" else corrected_train
                    diagnostic = raw_diag if branch == "raw" else corrected_diag
                    fit = fit_ratios(times, observed, output_dir)
                    fit_hash = digest(output_dir / "fit.json")
                    model = EffectiveModel(fit["ratios"], cells=48)
                    predicted_train = model.solve(CALIBRATION_POWERS, knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-9, atol=1e-10)
                    predicted_diag = model.solve(DIAGNOSTIC_POWERS, knots=DIAGNOSTIC_KNOTS, sample_step=5, rtol=1e-9, atol=1e-10)
                    train_residual = sensor_values(model, predicted_train)[1:] - observed
                    diag_residual = sensor_values(model, predicted_diag)[1:] - diagnostic
                    train_alarm = residual_alarm(train_residual, fit["success"])
                    diag_alarm = residual_alarm(diag_residual)
                    alarm = {"training": train_alarm, "diagnostic": diag_alarm,
                             "combined": train_alarm["alarm"] or diag_alarm["alarm"]}
                    write_json(output_dir / "alarm.json", alarm)
                    alarm_hash = digest(output_dir / "alarm.json")
                    np.savez_compressed(output_dir / "residuals.npz", training=train_residual, diagnostic=diag_residual)
                    prediction = EffectiveModel(fit["ratios"], cells=96).solve(process, sample_step=.25, rtol=1e-10, atol=1e-11)
                    with np.load(shared / "truth.npz") as truth:
                        score = prediction_score(truth["temperature"], prediction["temperature"])
                    np.savez_compressed(output_dir / "prediction.npz", time=prediction["time"], temperature=prediction["temperature"])
                    assert digest(folder / "offset.json") == offset_hash and digest(output_dir / "fit.json") == fit_hash and digest(output_dir / "alarm.json") == alarm_hash
                    case = {"key": branch_key(index, replicate, scenario, branch), "object": index, "replicate": replicate,
                            "scenario": scenario, "branch": branch, "offset": estimate, "offset_hash": offset_hash,
                            "fit": fit, "fit_hash": fit_hash, "alarm": alarm, "alarm_hash": alarm_hash, "score": score}
                    write_json(output_dir / "case.json", case)
                    cases.append(case)
                    print(f"CASE {index}/{replicate}/{scenario}/{branch}: residual={train_alarm['rmse_K']:.4f}/{diag_alarm['rmse_K']:.4f}K hidden={score['rmse_K']:.4f}K alarm={alarm['combined']} bad={score['inadequate']}", flush=True)
    selected = refinement_keys(cases)
    write_json(results / "refinement-selection.json", selected)
    for key in selected:
        folder = results / key
        case = next(item for item in cases if item["key"] == key)
        if (folder / "refinement.json").exists():
            continue
        _, truth, energy = physical(objects[case["object"]], "clean", process, [0, 60, 120, 180], cells=192, step=.0625)
        prediction = EffectiveModel(case["fit"]["ratios"], cells=192).solve(process, sample_step=.0625, rtol=1e-10, atol=1e-11)
        fine_score = prediction_score(truth["temperature"], prediction["temperature"])
        changes = {name: fine_score[name] - case["score"][name] for name in ["rmse_K", "final_mean_error_K"]}
        assert max(abs(value) for value in changes.values()) < .01
        refined = {"score": fine_score, "changes": changes, "energy": energy,
                   "label_flip": fine_score["inadequate"] != case["score"]["inadequate"]}
        np.savez_compressed(folder / "refined.npz", truth=truth["temperature"], prediction=prediction["temperature"], time=truth["time"])
        if case["score"]["inadequate"] and not case["alarm"]["combined"]:
            model = EffectiveModel(case["fit"]["ratios"], cells=96)
            training = model.solve(CALIBRATION_POWERS, knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-10, atol=1e-11)
            diagnostic = model.solve(DIAGNOSTIC_POWERS, knots=DIAGNOSTIC_KNOTS, sample_step=5, rtol=1e-10, atol=1e-11)
            with np.load(folder.parent / "readings.npz") as data:
                train_residual = sensor_values(model, training)[1:] - data["corrected_train"]
                diag_residual = sensor_values(model, diagnostic)[1:] - data["corrected_diag"]
            train_alarm = residual_alarm(train_residual, case["fit"]["success"])
            diag_alarm = residual_alarm(diag_residual)
            refined["alarm96"] = {"training": train_alarm, "diagnostic": diag_alarm, "combined": train_alarm["alarm"] or diag_alarm["alarm"]}
            np.savez_compressed(folder / "alarm96.npz", training=train_residual, diagnostic=diag_residual)
        write_json(folder / "refinement.json", refined)
        print(f"REFINE {key}: {changes} flip={refined['label_flip']}", flush=True)
    groups = {}
    for scenario in SCENARIOS:
        groups[scenario] = {}
        for branch in ["raw", "corrected"]:
            subset = [case for case in cases if case["scenario"] == scenario and case["branch"] == branch]
            counts = dict.fromkeys(["TP", "FP", "FN", "TN"], 0)
            for case in subset:
                alarm, bad = case["alarm"]["combined"], case["score"]["inadequate"]
                counts["TP" if alarm and bad else "FP" if alarm else "FN" if bad else "TN"] += 1
            groups[scenario][branch] = {"count": len(subset), "fit_success": sum(case["fit"]["success"] for case in subset),
                                       "rmse_range_K": [min(case["score"]["rmse_K"] for case in subset), max(case["score"]["rmse_K"] for case in subset)],
                                       "confusion": counts}
    summary = {"status": "COMPLETED", "groups": groups, "refinements": selected,
               "fit_calls": sum(case["fit"]["actual_solver_calls"] for case in cases),
               "fit_seconds": sum(case["fit"]["wall_seconds"] for case in cases), "wall_seconds": time.perf_counter() - start}
    write_json(results / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
