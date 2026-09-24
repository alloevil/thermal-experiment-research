import ast
import hashlib
import json
import os
from dataclasses import replace

os.environ["MPLBACKEND"] = "Agg"

from run import (ROOT, SCENARIOS, FACTOR_NAMES, refinement_keys, branch_key,
                 CALIBRATION_KNOTS, CALIBRATION_POWERS, DIAGNOSTIC_KNOTS, DIAGNOSTIC_POWERS, np)
from effective import HeatingModel, Parameters, sensor_prediction
from scipy.stats import qmc
import matplotlib.pyplot as plt


def load(path):
    return json.loads(path.read_text())


def score(truth, prediction):
    rmse = float(np.sqrt(np.mean((truth - prediction)**2)))
    final = float(abs(truth[-1].mean() - prediction[-1].mean()))
    return {"rmse_K": rmse, "final_mean_error_K": final, "inadequate": rmse > .5 or final > 1}


def alarm(residual, success=True):
    rmse = float(np.sqrt(np.mean(residual**2)))
    mean = float(np.max(abs(residual.mean(axis=0))))
    return bool(not success or rmse > .2 or mean > .2), rmse, mean


def main():
    results = ROOT / "results"
    config, summary = load(results / "config.json"), load(results / "summary.json")
    for name, expected in config["hashes"].items():
        path = ROOT / name if "/" not in name else ROOT.parent / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    functions = ast.parse((ROOT / "correction.py").read_text())
    estimator = next(node for node in functions.body if isinstance(node, ast.FunctionDef) and node.name == "estimate_offset")
    assert [arg.arg for arg in estimator.args.args] == ["sensor_readings_K", "reference_readings_K"]
    assert not {node.id for node in ast.walk(estimator) if isinstance(node, ast.Name)}.intersection({"scenario", "truth", "factors", "bias"})
    assert load(results / "correction-checks.json")["status"] == "PASS"
    objects = [dict(zip(FACTOR_NAMES, row.tolist(), strict=True)) for row in
               .9 + .2 * qmc.Sobol(5, scramble=True, seed=20260928).random_base2(1)]
    assert config["objects"] == objects and config["scenarios"] == SCENARIOS
    cases, offset_records = [], []
    replay_checks = []
    for index, factors in enumerate(objects):
        shared = results / f"object-{index}"
        params = Parameters()
        model = HeatingModel(96, parameters=replace(params, **{name: getattr(params, name) * value
                                                              for name, value in factors.items() if name != "power_gain"}))
        for name, command, knots in [("training", CALIBRATION_POWERS, CALIBRATION_KNOTS),
                                     ("diagnostic", DIAGNOSTIC_POWERS, DIAGNOSTIC_KNOTS),
                                     ("truth", np.array(config["process_powers"]), np.array([0, 60, 120, 180]))]:
            with np.load(shared / f"{name}.npz") as data:
                fields, times, ledger = data["temperature"], data["time"], data["ledger"]
                assert np.isfinite(fields).all() and fields.min() > 0
                actual = command * factors["power_gain"]
                assert actual.min() >= 0 and actual.max() <= 1
                assert np.max(abs(np.diff(actual, axis=0) / np.diff(knots)[:, None])) <= .015 + 1e-9
                stored = model.cell_capacity * np.sum(fields - params.ambient, axis=1)
                assert np.max(abs(stored - ledger[:, 0] + ledger[:, 1] + ledger[:, 2])) < 1e-4
                absorbed = np.trapezoid(actual.sum(axis=1), knots)
                assert abs(absorbed - ledger[-1, 0]) < 1e-4
                convection, radiation = model.losses(fields)
                assert abs(absorbed - np.trapezoid((convection + radiation).sum(axis=1), times) - stored[-1]) < .1
                predicted_sensors = np.array([np.interp(params.length * np.array([.15, .5, .85]), model.coordinates, field) for field in fields])
                np.testing.assert_allclose(predicted_sensors, data["sensors"], rtol=0, atol=1e-10)
        with np.load(shared / "training.npz") as data:
            clean_train = data["sensors"][1:]
        with np.load(shared / "diagnostic.npz") as data:
            clean_diag = data["sensors"][1:]
        with np.load(shared / "truth.npz") as data:
            truth = data["temperature"]
        for replicate in range(2):
            seed = 20260928 + 100 * index + 10 * replicate
            anchor_noise = np.random.default_rng(seed).normal(0, .1, (10, 3))
            reference_noise = np.random.default_rng(seed + 1).normal(0, .05, 10)
            train_noise = np.random.default_rng(seed + 2).normal(0, .1, (48, 3))
            diag_noise = np.random.default_rng(seed + 3).normal(0, .1, (48, 3))
            for scenario in SCENARIOS:
                folder = shared / f"noise-{replicate}-{scenario}"
                fixed_bias = 0 if scenario == "clean" else (.4 if index == 0 else -.4)
                reference_bias = .35 if scenario == "reference_bias" else 0
                estimate = load(folder / "offset.json")
                with np.load(folder / "readings.npz") as readings:
                    np.testing.assert_array_equal(readings["anchor"], 296.15 + fixed_bias + anchor_noise)
                    np.testing.assert_array_equal(readings["reference"], 296.15 + reference_bias + reference_noise)
                    differences = readings["anchor"] - readings["reference"][:, None]
                    means = differences.sum(axis=0) / 10
                    std = np.sqrt(((differences - means)**2).sum(axis=0) / 9)
                    np.testing.assert_allclose(means, estimate["offset_K"], rtol=0, atol=1e-12)
                    np.testing.assert_allclose(std, estimate["difference_sample_std_K"], rtol=0, atol=1e-12)
                    np.testing.assert_allclose(std / np.sqrt(10), estimate["mean_standard_error_K"], rtol=0, atol=1e-12)
                    assert estimate["samples"] == 10
                    for name, clean, noise in [("train", clean_train, train_noise), ("diag", clean_diag, diag_noise)]:
                        drift = .008 * (clean - 296.15) if scenario == "thermal_drift" else 0
                        np.testing.assert_array_equal(readings[f"raw_{name}"], clean + fixed_bias + drift + noise)
                        np.testing.assert_allclose(readings[f"corrected_{name}"], readings[f"raw_{name}"] - means, rtol=0, atol=1e-12)
                    observed_train = {branch: readings[f"{branch}_train"].copy() for branch in ["raw", "corrected"]}
                offset_records.append({"object": index, "replicate": replicate, "scenario": scenario,
                                       "offset_error_vs_fixed_bias_K": (means - fixed_bias).tolist(),
                                       "reported_standard_errors_K": estimate["mean_standard_error_K"]})
                for branch in ["raw", "corrected"]:
                    output_dir = folder / branch
                    case = load(output_dir / "case.json")
                    assert case["key"] == branch_key(index, replicate, scenario, branch)
                    for name in ["fit", "alarm"]:
                        assert case[f"{name}_hash"] == hashlib.sha256((output_dir / f"{name}.json").read_bytes()).hexdigest()
                        assert case[name] == load(output_dir / f"{name}.json")
                    assert case["offset_hash"] == hashlib.sha256((folder / "offset.json").read_bytes()).hexdigest()
                    calls = [json.loads(line) for line in (output_dir / "fit-calls.jsonl").read_text().splitlines()]
                    assert len(calls) == case["fit"]["actual_solver_calls"]
                    assert [item["call"] for item in calls] == list(range(1, len(calls) + 1))
                    assert case["fit"]["scipy_nfev"] <= 40
                    with np.load(output_dir / "residuals.npz") as residuals:
                        train_decision, train_rmse, _ = alarm(residuals["training"], case["fit"]["success"])
                        diag_decision, _, _ = alarm(residuals["diagnostic"])
                        assert train_decision == case["alarm"]["training"]["alarm"]
                        assert diag_decision == case["alarm"]["diagnostic"]["alarm"]
                        assert case["alarm"]["combined"] == (train_decision or diag_decision)
                        assert np.isclose(train_rmse, case["fit"]["train_rmse_K"], atol=1e-7)
                        if index == 0 and replicate == 0:
                            _, replay = sensor_prediction(case["fit"]["ratios"])
                            difference = float(np.max(abs(replay - observed_train[branch] - residuals["training"])))
                            assert difference < 1e-7
                            replay_checks.append({"key": case["key"], "difference_K": difference})
                    with np.load(output_dir / "prediction.npz") as data:
                        assert data["temperature"].shape == (721, 96) and np.isfinite(data["temperature"]).all()
                        error = float(np.sqrt(np.mean((truth - data["temperature"])**2)))
                        final = float(abs(truth[-1].mean() - data["temperature"][-1].mean()))
                        assert np.isclose(error, case["score"]["rmse_K"])
                        assert np.isclose(final, case["score"]["final_mean_error_K"])
                        assert case["score"]["inadequate"] == (error > .5 or final > 1)
                    cases.append(case)
            for scenario in ["stable", "reference_bias", "thermal_drift"]:
                with np.load(shared / f"noise-{replicate}-clean/readings.npz") as clean, np.load(shared / f"noise-{replicate}-{scenario}/readings.npz") as other:
                    if scenario == "stable":
                        np.testing.assert_allclose(clean["corrected_train"], other["corrected_train"], atol=1e-10, rtol=0)
                        np.testing.assert_allclose(clean["corrected_diag"], other["corrected_diag"], atol=1e-10, rtol=0)
            with np.load(shared / f"noise-{replicate}-stable/readings.npz") as stable, np.load(shared / f"noise-{replicate}-reference_bias/readings.npz") as wrong:
                np.testing.assert_array_equal(stable["raw_train"], wrong["raw_train"])
                np.testing.assert_array_equal(stable["raw_diag"], wrong["raw_diag"])
                np.testing.assert_allclose(wrong["corrected_train"] - stable["corrected_train"], .35, rtol=0, atol=1e-10)
                np.testing.assert_allclose(wrong["corrected_diag"] - stable["corrected_diag"], .35, rtol=0, atol=1e-10)
                stable_offset = load(shared / f"noise-{replicate}-stable/offset.json")
                wrong_offset = load(shared / f"noise-{replicate}-reference_bias/offset.json")
                np.testing.assert_allclose(stable_offset["mean_standard_error_K"], wrong_offset["mean_standard_error_K"], atol=1e-12, rtol=0)
    assert len(cases) == 32 and len({case["key"] for case in cases}) == 32
    for scenario in SCENARIOS:
        for branch in ["raw", "corrected"]:
            subset = [case for case in cases if case["scenario"] == scenario and case["branch"] == branch]
            expected = summary["groups"][scenario][branch]
            assert expected["count"] == len(subset) == 4
            assert expected["fit_success"] == sum(case["fit"]["success"] for case in subset)
            counts = dict.fromkeys(["TP", "FP", "FN", "TN"], 0)
            for case in subset:
                warned, bad = case["alarm"]["combined"], case["score"]["inadequate"]
                counts["TP" if warned and bad else "FP" if warned else "FN" if bad else "TN"] += 1
            assert counts == expected["confusion"]
    selected = refinement_keys(cases)
    assert selected == summary["refinements"] == load(results / "refinement-selection.json")
    misses, flips, changes = [], [], []
    for key in selected:
        case = next(item for item in cases if item["key"] == key)
        folder = results / key
        refined = load(folder / "refinement.json")
        with np.load(folder / "refined.npz") as data:
            assert data["truth"].shape == (2881, 192)
            error = float(np.sqrt(np.mean((data["truth"] - data["prediction"])**2)))
            final = float(abs(data["truth"][-1].mean() - data["prediction"][-1].mean()))
        for name, value in [("rmse_K", error), ("final_mean_error_K", final)]:
            assert np.isclose(value, refined["score"][name])
            change = value - case["score"][name]
            assert abs(change) < .01 and np.isclose(change, refined["changes"][name])
            changes.append(abs(change))
        bad = error > .5 or final > 1
        assert refined["label_flip"] == (bad != case["score"]["inadequate"])
        if refined["label_flip"]:
            flips.append(key)
        if case["score"]["inadequate"] and not case["alarm"]["combined"]:
            with np.load(folder / "alarm96.npz") as data:
                decision = alarm(data["training"], case["fit"]["success"])[0] or alarm(data["diagnostic"])[0]
            assert decision == refined["alarm96"]["combined"]
            if bad and not decision:
                misses.append(key)
    verification = {"status": "PASS", "cases": 32, "offset_checks": offset_records,
                    "fit_replays": replay_checks, "persistent_corrected_misses": misses,
                    "refinement_flips": flips, "max_refinement_change_K": max(changes)}
    (results / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    print("PASS frozen protocol/model/fitter/detector and 32 paired branches")
    print("PASS synchronized anchor/noise reconstruction, offset and standard-error arithmetic")
    print("PASS sole reference-error/drift changes; no physical truth used by estimator")
    print("PASS power, energy, hidden scores, residual rules and confusion recount")
    print(f"PASS {len(replay_checks)} final fit replays; {len(selected)} refinements; {len(misses)} persistent corrected misses")
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    colors = ["#488567", "#3979a9", "#c27336", "#996094"]
    for scenario, color in zip(SCENARIOS, colors, strict=True):
        for index in range(2):
            for replicate in range(2):
                pair = [next(item for item in cases if item["key"] == branch_key(index, replicate, scenario, branch)) for branch in ["raw", "corrected"]]
                axes[0].plot([0, 1], [item["score"]["rmse_K"] for item in pair], "o-", color=color, alpha=.7,
                             label=scenario if index == replicate == 0 else None)
    axes[0].axhline(.5, color="black", linestyle="--", linewidth=1)
    axes[0].set(xticks=[0, 1], xticklabels=["Raw", "Offset-corrected"], ylabel="Hidden field RMSE (K)", title="Same physical object and noisy observations")
    axes[0].legend(fontsize=8)
    positions = np.arange(4)
    for shift, branch, color in [(-.18, "raw", "#3979a9"), (.18, "corrected", "#488567")]:
        counts = [summary["groups"][scenario][branch]["confusion"]["FN"] for scenario in SCENARIOS]
        axes[1].bar(positions + shift, counts, width=.36, color=color, label=branch)
    axes[1].set(xticks=positions, xticklabels=["Clean", "Stable", "Bad reference", "Thermal drift"],
                title="Missed inadequate predictions", ylabel="Count / 4 cases", ylim=(0, 4.5))
    axes[1].legend(fontsize=8)
    for position, scenario, color in zip(positions, SCENARIOS, colors, strict=True):
        subset = [item for item in offset_records if item["scenario"] == scenario]
        for item in subset:
            axes[2].errorbar(position, np.mean(item["offset_error_vs_fixed_bias_K"]),
                             yerr=np.mean(item["reported_standard_errors_K"]), fmt="o", color=color, alpha=.7)
    axes[2].axhline(0, color="black", linewidth=1)
    axes[2].set(xticks=positions, xticklabels=["Clean", "Stable", "Bad reference", "Thermal drift"],
                title="Offset estimate error; bars = mean channel SE", ylabel="Error relative to fixed sensor bias (K)")
    for axis in axes:
        axis.grid(alpha=.2)
    figure.suptitle("One-point reference correction: synthetic equilibrium and noise assumptions, not metrology certification", fontsize=12)
    figure.savefig(results / "reference-correction.png", dpi=150)
    plt.close(figure)
    print("PASS results/reference-correction.png rendered")


if __name__ == "__main__":
    main()
