import ast
import hashlib
import json
import os

os.environ["MPLBACKEND"] = "Agg"

from experiment import (
    ROOT, SCENARIOS, FACTOR_NAMES, CALIBRATION_KNOTS, CALIBRATION_POWERS,
    DIAGNOSTIC_KNOTS, DIAGNOSTIC_POWERS, check_lag, np, physical, sensor_values,
)
from scipy.stats import qmc
from scipy.signal import lsim
import matplotlib.pyplot as plt


def load_json(path):
    return json.loads(path.read_text())


def independent_rule(residual, success=True):
    rmse = float(np.linalg.norm(residual) / np.sqrt(residual.size))
    mean_bias = float(np.max(abs(residual.mean(axis=0))))
    return (not success) or rmse > .2 or mean_bias > .2, rmse, mean_bias


def main():
    results = ROOT / "results"
    config = load_json(results / "config.json")
    summary = load_json(results / "summary.json")
    for name, expected in config["hashes"].items():
        source = ROOT / name if "/" not in name else ROOT.parent / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, name
    expected_objects = [dict(zip(FACTOR_NAMES, row.tolist(), strict=True)) for row in
                        .9 + .2 * qmc.Sobol(5, scramble=True, seed=20260926).random_base2(2)]
    assert config["objects"] == expected_objects
    tree = ast.parse((ROOT / "experiment.py").read_text())
    detector = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "residual_alarm")
    assert [arg.arg for arg in detector.args.args] == ["residual", "fit_success"]
    assert not {node.id for node in ast.walk(detector) if isinstance(node, ast.Name)}.intersection({"scenario", "truth", "score", "factors"})
    assert check_lag()["status"] == "PASS"
    cases = []
    signal_checks = []
    for index, factors in enumerate(config["objects"]):
        train_noise = np.random.default_rng(20260926 + 100 * index).normal(0, .1, (48, 3))
        diag_noise = np.random.default_rng(20260927 + 100 * index).normal(0, .1, (48, 3))
        for scenario in SCENARIOS:
            folder = results / f"object-{index}-{scenario}"
            case = load_json(folder / "case.json")
            assert case["object"] == index and case["scenario"] == scenario
            assert hashlib.sha256((folder / "fit.json").read_bytes()).hexdigest() == case["fit_frozen_sha256"]
            assert hashlib.sha256((folder / "alarm.json").read_bytes()).hexdigest() == case["alarm_frozen_sha256"]
            assert load_json(folder / "fit.json") == case["fit"] and load_json(folder / "alarm.json") == case["alarm"]
            calls = [json.loads(line) for line in (folder / "fit-calls.jsonl").read_text().splitlines()]
            assert len(calls) == case["fit"]["actual_solver_calls"]
            assert [call["call"] for call in calls] == list(range(1, len(calls) + 1))
            assert case["fit"]["scipy_nfev"] <= 40
            with np.load(folder / "training.npz") as training, np.load(folder / "train-prediction.npz") as prediction:
                np.testing.assert_array_equal(training["noise"], train_noise)
                np.testing.assert_array_equal(training["noisy"], training["distorted"] + train_noise)
                np.testing.assert_array_equal(training["time"], np.arange(5, 241, 5))
                train_residual = prediction["predicted"] - training["noisy"]
                train_alarm, train_rmse, train_bias = independent_rule(train_residual, case["fit"]["success"])
                assert np.isclose(train_rmse, case["fit"]["train_rmse_K"], atol=1e-7)
            with np.load(folder / "diagnostic.npz") as diagnostic:
                np.testing.assert_array_equal(diagnostic["noise"], diag_noise)
                np.testing.assert_array_equal(diagnostic["measured"], diagnostic["distorted"] + diag_noise)
                diag_residual = diagnostic["predicted"] - diagnostic["measured"]
                diag_alarm, diag_rmse, diag_bias = independent_rule(diag_residual)
            for name, alarm, rmse, mean_bias in [("training", train_alarm, train_rmse, train_bias), ("diagnostic", diag_alarm, diag_rmse, diag_bias)]:
                assert case["alarm"][name]["alarm"] == alarm
                assert np.isclose(case["alarm"][name]["rmse_K"], rmse)
                assert np.isclose(case["alarm"][name]["max_sensor_mean_residual_K"], mean_bias)
            assert case["alarm"]["combined_alarm"] == (train_alarm or diag_alarm)
            with np.load(folder / "evaluation.npz") as evaluation:
                assert evaluation["truth"].shape == evaluation["prediction"].shape == (721, 96)
                assert np.isfinite(evaluation["truth"]).all() and np.isfinite(evaluation["prediction"]).all()
                rmse = float(np.sqrt(np.mean((evaluation["truth"] - evaluation["prediction"])**2)))
                final_error = float(abs(evaluation["truth"][-1].mean() - evaluation["prediction"][-1].mean()))
                assert np.isclose(case["score"]["rmse_K"], rmse) and np.isclose(case["score"]["final_mean_error_K"], final_error)
                assert case["score"]["inadequate"] == (rmse > .5 or final_error > 1)
            for energy_name in ["training_energy", "diagnostic_energy", "evaluation_energy"]:
                assert case[energy_name]["max_balance_J"] < 1e-4 and abs(case[energy_name]["external_balance_J"]) < .1
            if scenario in ["bias", "lag"]:
                with np.load(results / f"object-{index}-clean/evaluation.npz") as clean, np.load(folder / "evaluation.npz") as other:
                    np.testing.assert_allclose(other["truth"], clean["truth"], atol=1e-8, rtol=0)
            if scenario == "bias":
                for file, key in [("training.npz", "distorted"), ("diagnostic.npz", "distorted")]:
                    with np.load(results / f"object-{index}-clean" / file) as clean, np.load(folder / file) as biased:
                        np.testing.assert_allclose(biased[key] - clean[key], .5, rtol=0, atol=1e-10)
            if index == 0:
                refined = case["refinement"]
                assert max(abs(value) for value in refined["differences"].values()) < .01
                assert refined["classification_changed"] == (refined["score"]["inadequate"] != case["score"]["inadequate"])
                for label, powers, knots, file in [("training", CALIBRATION_POWERS, CALIBRATION_KNOTS, "training.npz"),
                                                   ("diagnostic", DIAGNOSTIC_POWERS, DIAGNOSTIC_KNOTS, "diagnostic.npz")]:
                    model, reproduced, energy = physical(factors, scenario, powers, knots)
                    ideal = sensor_values(model, reproduced)
                    if scenario == "lag":
                        alternate = np.column_stack([lsim(([1], [8, 1]), U=ideal[:, sensor] - 296.15,
                                                           T=reproduced["time"])[1] + 296.15 for sensor in range(3)])
                    else:
                        alternate = ideal + (.5 if scenario == "bias" else 0)
                    sampled = np.array([np.interp(np.arange(5, 241, 5), reproduced["time"], alternate[:, sensor]) for sensor in range(3)]).T
                    with np.load(folder / file) as recorded:
                        difference = float(np.max(abs(sampled - recorded["distorted"])))
                    assert difference < 1e-7
                    signal_checks.append({"scenario": scenario, "trace": label, "max_difference_K": difference})
            cases.append(case)
    assert len(cases) == 16
    matrices = {}
    for rule in ["training", "combined"]:
        counts = dict.fromkeys(["TP", "FP", "FN", "TN"], 0)
        for case in cases:
            alarm = case["alarm"]["training"]["alarm"] if rule == "training" else case["alarm"]["combined_alarm"]
            truth = case["score"]["inadequate"]
            name = "TP" if alarm and truth else "FP" if alarm else "FN" if truth else "TN"
            counts[name] += 1
        assert counts == summary["confusion_vs_hidden_prediction"][rule]
        matrices[rule] = counts
    for scenario in SCENARIOS:
        subset = [case for case in cases if case["scenario"] == scenario]
        assert len(subset) == summary["groups"][scenario]["count"] == 4
        for key, predicate in [("fit_success", lambda case: case["fit"]["success"]),
                               ("training_alarms", lambda case: case["alarm"]["training"]["alarm"]),
                               ("combined_alarms", lambda case: case["alarm"]["combined_alarm"]),
                               ("inadequate_predictions", lambda case: case["score"]["inadequate"])]:
            assert sum(predicate(case) for case in subset) == summary["groups"][scenario][key]
    print("PASS frozen protocol, paired designs, sources, fitting budgets and immutable alarms")
    print("PASS training/diagnostic common noise, residual rules and independent held-out scoring")
    print("PASS clean/bias/lag share true physics; offset is exactly 0.5K")
    print("PASS sensor lag vs analytic tests and independent scipy.signal.lsim for object 0")
    print("PASS four predefined refinement checks; false alarms/misses preserved")
    verification = {"status": "PASS", "cases": len(cases), "independent_signal_checks": signal_checks,
                    "confusion": matrices, "refinement_flips": [case["scenario"] for case in cases if case["refinement"] and case["refinement"]["classification_changed"]]}
    (results / "verification.json").write_text(json.dumps(verification, indent=2) + "\n")
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.7), constrained_layout=True)
    for scenario, color in zip(SCENARIOS, ["#358664", "#b97925", "#a74545", "#4265a8"], strict=True):
        subset = [case for case in cases if case["scenario"] == scenario]
        axes[0].scatter([case["alarm"]["training"]["rmse_K"] for case in subset],
                        [case["score"]["rmse_K"] for case in subset], label=scenario, color=color)
        axes[1].scatter([case["alarm"]["diagnostic"]["rmse_K"] for case in subset],
                        [case["score"]["rmse_K"] for case in subset], label=scenario, color=color)
    for index, title in enumerate(["Training residual alone", "Additional diagnostic residual"]):
        axes[index].axvline(.2, linestyle="--", color="gray")
        axes[index].axhline(.5, linestyle="--", color="gray")
        axes[index].set(xlabel="Observed residual RMSE (K)", ylabel="Hidden process field RMSE (K)", title=title)
        axes[index].grid(alpha=.2)
    axes[0].legend(fontsize=8)
    positions = np.arange(4)
    for shift, rule, color in [(-.18, "training", "#4265a8"), (.18, "combined", "#358664")]:
        values = [matrices[rule][name] for name in ["TP", "FP", "FN", "TN"]]
        axes[2].bar(positions + shift, values, width=.36, label=rule, color=color)
        for position, value in zip(positions + shift, values, strict=True):
            axes[2].text(position, value + .1, str(value), ha="center")
    axes[2].set(xticks=positions, xticklabels=["Detected", "False alarm", "Missed", "Correct pass"], ylabel="Case count",
                title="Versus fixed hidden-prediction adequacy label", ylim=(0, 17))
    axes[2].legend(fontsize=8)
    figure.suptitle("Unknown model/sensor mismatch: 4 paired objects; warnings are not safety certification", fontsize=12)
    figure.savefig(results / "mismatch.png", dpi=150)
    plt.close(figure)
    print("PASS results/mismatch.png rendered")


if __name__ == "__main__":
    main()
