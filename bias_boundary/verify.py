import hashlib
import json
import os
from dataclasses import replace

os.environ["MPLBACKEND"] = "Agg"

from run import (ROOT, BIASES, FACTOR_NAMES, CALIBRATION_KNOTS, CALIBRATION_POWERS,
                 DIAGNOSTIC_KNOTS, DIAGNOSTIC_POWERS, identify, candidates_for_refinement, np)
from effective import HeatingModel, Parameters
from scipy.stats import qmc
import matplotlib.pyplot as plt


def read_json(path):
    return json.loads(path.read_text())


def rule(residual, success=True):
    return not success or np.sqrt(np.mean(residual**2)) > .2 or np.max(abs(residual.mean(axis=0))) > .2


def score(truth, prediction):
    rmse = float(np.sqrt(np.mean((truth - prediction)**2)))
    final = float(abs(truth[-1].mean() - prediction[-1].mean()))
    return {"rmse_K": rmse, "final_mean_error_K": final, "inadequate": rmse > .5 or final > 1}


def main():
    results = ROOT / "results"
    config, summary = read_json(results / "config.json"), read_json(results / "summary.json")
    for name, expected in config["hashes"].items():
        path = ROOT / name if "/" not in name else ROOT.parent / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    expected_objects = [dict(zip(FACTOR_NAMES, row.tolist(), strict=True)) for row in
                        .9 + .2 * qmc.Sobol(5, scramble=True, seed=20260927).random_base2(1)]
    assert expected_objects == config["objects"] and config["biases_K"] == BIASES
    cases = []
    for index, factors in enumerate(config["objects"]):
        params = Parameters()
        model = HeatingModel(96, parameters=replace(params, **{name: getattr(params, name) * value
                                                              for name, value in factors.items() if name != "power_gain"}))
        shared = results / f"object-{index}"
        for name, commands, knots in [("training", CALIBRATION_POWERS, CALIBRATION_KNOTS),
                                      ("diagnostic", DIAGNOSTIC_POWERS, DIAGNOSTIC_KNOTS),
                                      ("truth", np.array(config["process_powers"]), np.array([0, 60, 120, 180]))]:
            with np.load(shared / f"{name}.npz") as data:
                actual = commands * factors["power_gain"]
                assert actual.min() >= 0 and actual.max() <= 1
                assert np.max(abs(np.diff(actual, axis=0) / np.diff(knots)[:, None])) <= .015 + 1e-9
                field, ledger, times = data["temperature"], data["ledger"], data["time"]
                assert np.isfinite(field).all() and field.min() > 0
                stored = model.cell_capacity * (field - params.ambient).sum(axis=1)
                assert np.max(abs(stored - ledger[:, 0] + ledger[:, 1] + ledger[:, 2])) < 1e-4
                absorbed = np.trapezoid(actual.sum(axis=1), knots)
                assert abs(absorbed - ledger[-1, 0]) < 1e-4
                convective, radiative = model.losses(field)
                assert abs(absorbed - np.trapezoid((convective + radiative).sum(axis=1), times) - stored[-1]) < .1
                positions = params.length * np.array([.15, .5, .85])
                sensors = np.array([np.interp(positions, model.coordinates, item) for item in field])
                np.testing.assert_allclose(sensors, data["sensors"], atol=1e-10, rtol=0)
        with np.load(shared / "training.npz") as data:
            clean_train = data["sensors"][1:]
        with np.load(shared / "diagnostic.npz") as data:
            clean_diag = data["sensors"][1:]
        with np.load(shared / "truth.npz") as data:
            truth = data["temperature"]
        for replicate in range(2):
            train_noise = np.random.default_rng(20260927 + 100 * index + 10 * replicate).normal(0, .1, (48, 3))
            diag_noise = np.random.default_rng(20260928 + 100 * index + 10 * replicate).normal(0, .1, (48, 3))
            for bias in BIASES:
                case_id = identify(index, replicate, bias)
                folder = results / case_id
                case = read_json(folder / "case.json")
                assert case["id"] == case_id and case["bias_K"] == bias
                assert case["fit_hash"] == hashlib.sha256((folder / "fit.json").read_bytes()).hexdigest()
                assert case["alarm_hash"] == hashlib.sha256((folder / "alarm.json").read_bytes()).hexdigest()
                assert case["fit"] == read_json(folder / "fit.json") and case["alarm"] == read_json(folder / "alarm.json")
                calls = [json.loads(line) for line in (folder / "fit-calls.jsonl").read_text().splitlines()]
                assert len(calls) == case["fit"]["actual_solver_calls"]
                assert [item["call"] for item in calls] == list(range(1, len(calls) + 1))
                assert case["fit"]["scipy_nfev"] <= 40
                with np.load(folder / "observations.npz") as data:
                    np.testing.assert_array_equal(data["training_noise"], train_noise)
                    np.testing.assert_array_equal(data["diagnostic_noise"], diag_noise)
                    np.testing.assert_array_equal(data["training"], clean_train + bias + train_noise)
                    np.testing.assert_array_equal(data["diagnostic"], clean_diag + bias + diag_noise)
                    train_residual = data["training_prediction"] - data["training"]
                    diag_residual = data["diagnostic_prediction"] - data["diagnostic"]
                    train_alarm = rule(train_residual, case["fit"]["success"])
                    diagnostic_alarm = rule(diag_residual)
                    assert case["alarm"]["training"]["alarm"] == train_alarm
                    assert case["alarm"]["diagnostic"]["alarm"] == diagnostic_alarm
                    assert case["alarm"]["combined"] == (train_alarm or diagnostic_alarm)
                    for name, residual in [("training", train_residual), ("diagnostic", diag_residual)]:
                        assert np.isclose(case["alarm"][name]["rmse_K"], np.sqrt(np.mean(residual**2)))
                        assert np.isclose(case["alarm"][name]["max_sensor_mean_residual_K"], np.max(abs(residual.mean(axis=0))))
                    assert np.isclose(case["fit"]["train_rmse_K"], np.sqrt(np.mean(train_residual**2)), atol=1e-7)
                with np.load(folder / "prediction.npz") as data:
                    assert data["temperature"].shape == (721, 96)
                    computed = score(truth, data["temperature"])
                    for key in ["rmse_K", "final_mean_error_K"]:
                        assert np.isclose(computed[key], case["score"][key])
                    assert computed["inadequate"] == case["score"]["inadequate"]
                cases.append(case)
    assert len(cases) == summary["cases"] == 28
    assert sum(case["fit"]["actual_solver_calls"] for case in cases) == summary["fit_calls"]
    groups = {}
    for bias in BIASES:
        subset = [case for case in cases if case["bias_K"] == bias]
        assert len(subset) == 4
        group = {"count": 4, "inadequate": sum(case["score"]["inadequate"] for case in subset)}
        for name in ["training", "combined"]:
            counts = dict.fromkeys(["TP", "FP", "FN", "TN"], 0)
            for case in subset:
                alarm = case["alarm"]["training"]["alarm"] if name == "training" else case["alarm"]["combined"]
                bad = case["score"]["inadequate"]
                counts["TP" if alarm and bad else "FP" if alarm else "FN" if bad else "TN"] += 1
            group[name] = counts
        assert group == summary["groups"][str(bias)]
        groups[str(bias)] = group
    selected = candidates_for_refinement(cases)
    assert selected == summary["refinements"] == read_json(results / "refinement-selection.json")
    refined_misses, flips, changes = [], [], []
    for case_id in selected:
        folder = results / case_id
        case = next(item for item in cases if item["id"] == case_id)
        refined = read_json(folder / "refinement.json")
        with np.load(folder / "refined.npz") as data:
            assert data["truth"].shape == (2881, 192)
            fine = score(data["truth"], data["prediction"])
        for key in ["rmse_K", "final_mean_error_K"]:
            assert np.isclose(fine[key], refined["score"][key])
            difference = fine[key] - case["score"][key]
            assert abs(difference) < .01 and np.isclose(difference, refined["changes"][key])
            changes.append(abs(difference))
        assert refined["label_flipped"] == (fine["inadequate"] != case["score"]["inadequate"])
        if refined["label_flipped"]:
            flips.append(case_id)
        if case["score"]["inadequate"] and not case["alarm"]["combined"]:
            with np.load(folder / "alarm96.npz") as data:
                alarm = rule(data["train_residual"], case["fit"]["success"]) or rule(data["diagnostic_residual"])
            assert refined["alarm96"]["combined"] == alarm
            if not alarm and fine["inadequate"]:
                refined_misses.append(case_id)
    print("PASS frozen original detector/fitter and new 28-case paired design")
    print("PASS exact noise reconstruction, fixed physical fields and sole bias changes")
    print("PASS energy conservation and independent heat-flux integrals")
    print("PASS frozen fits/alarms, independently computed residuals, scores and confusion counts")
    print(f"PASS {len(selected)} selected refinements; {len(refined_misses)} persistent combined misses; {len(flips)} label flips")
    payload = {"status": "PASS", "groups": groups, "persistent_combined_misses": refined_misses,
               "refinement_label_flips": flips, "maximum_refinement_score_change_K": max(changes)}
    (results / "verification.json").write_text(json.dumps(payload, indent=2) + "\n")
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.6), constrained_layout=True)
    for index in range(2):
        for replicate in range(2):
            subset = sorted([case for case in cases if case["object"] == index and case["noise"] == replicate], key=lambda item: item["bias_K"])
            label = f"Object {index}, noise {replicate}"
            axes[0].plot(BIASES, [item["alarm"]["training"]["rmse_K"] for item in subset], "o-", label=label, markersize=4)
            axes[1].plot(BIASES, [item["score"]["rmse_K"] for item in subset], "o-", markersize=4)
    axes[0].axhline(.2, color="black", linestyle="--")
    axes[1].axhline(.5, color="black", linestyle="--")
    axes[0].set(title="Calibration residual (threshold unchanged)", ylabel="Residual RMSE (K)")
    axes[1].set(title="Hidden process prediction", ylabel="Field RMSE (K)")
    axes[0].legend(fontsize=7)
    positions = np.arange(len(BIASES))
    for shift, name in [(-.17, "training"), (.17, "combined")]:
        values = [groups[str(bias)][name]["FN"] for bias in BIASES]
        axes[2].bar(positions + shift, values, width=.34, label=name)
    axes[2].set(xticks=positions, xticklabels=[str(bias) for bias in BIASES], ylim=(0, 4.5),
                ylabel="Missed inadequate predictions / 4 cases", title="False negatives by fixed bias")
    axes[2].legend(fontsize=8)
    for axis in axes:
        axis.set_xlabel("Common sensor bias (K)")
        axis.grid(alpha=.2)
    figure.suptitle("Small-bias audit: fixed 0.2K warning rule; synthetic paired cases, not safety validation", fontsize=12)
    figure.savefig(results / "bias-boundary.png", dpi=150)
    plt.close(figure)
    print("PASS results/bias-boundary.png rendered")


if __name__ == "__main__":
    main()
