import hashlib
import json
import os
from collections import Counter
from pathlib import Path

os.environ["MPLBACKEND"] = "Agg"

from run_sensitivity import FACTORS, LIMITS, ROOT, RADIATION, Parameters, cases, np, select_refinements
from model import target
import matplotlib.pyplot as plt


def read_json(path):
    return json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def main():
    results = ROOT / "results"
    config = read_json(results / "config.json")
    for name, expected in config["hashes"].items():
        path = ROOT / name if name in ["protocol.md", "run_sensitivity.py"] else ROOT.parent / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, name
    assert config["cases"] == cases()
    records = [json.loads(line) for line in (results / "scan.jsonl").read_text().splitlines()]
    refinements = [json.loads(line) for line in (results / "refinements.jsonl").read_text().splitlines()]
    summary = read_json(results / "summary.json")
    assert len(records) == len({record["id"] for record in records}) == 181
    assert Counter(record["group"] for record in records) == {"nominal": 1, "oat": 20, "corners": 32, "sobol": 128}
    assert {record["id"] for record in records} == {case["id"] for case in config["cases"]}
    by_case = {case["id"]: case for case in config["cases"]}
    expected_params = Parameters().__dict__
    fixed_command = np.array(config["command_powers_W"])
    for record in records + refinements:
        assert record["factors"] == by_case[record["id"]]["factors"]
        for name, value in expected_params.items():
            multiplier = record["factors"].get(name, 1.0)
            assert record["parameters"][name] == value * multiplier, (record["id"], name)
        powers = np.array(record["actual_powers_W"])
        np.testing.assert_allclose(powers, fixed_command * record["factors"]["power_gain"], rtol=0, atol=0)
        assert powers.min() >= 0 and powers.max() <= 1
        assert np.max(abs(np.diff(powers, axis=0) / 60)) <= 0.015
        trace_path = ROOT / record["trace"]
        assert hashlib.sha256(trace_path.read_bytes()).hexdigest() == record["trace_sha256"]
        with np.load(trace_path, allow_pickle=False) as trace:
            elapsed = trace["time"]
            assert elapsed[0] == 0 and elapsed[-1] == 180
            assert len(elapsed) == (721 if record["cells"] == 96 else 2881)
            assert np.all(np.diff(elapsed) > 0)
            assert all(np.isfinite(trace[name]).all() for name in trace.files)
            assert trace["minimum"].min() > 0
            derived = {
                "mse_K2": np.trapezoid(trace["std"]**2 + (trace["mean"] - target(elapsed))**2, elapsed) / 180,
                "peak_K": trace["maximum"].max(), "max_spread_K": (trace["maximum"] - trace["minimum"]).max(),
                "final_mean_K": trace["mean"][-1], "final_std_K": trace["std"][-1],
            }
            for quantity, value in derived.items():
                assert np.isclose(value, record["metrics"][quantity], rtol=1e-10, atol=1e-10)
            heat_capacity = record["parameters"]["mass"] * record["parameters"]["heat_capacity"]
            stored = heat_capacity * (trace["mean"] - record["parameters"]["ambient"])
            balance = stored - trace["ledger"][:, 0] + trace["ledger"][:, 1] + trace["ledger"][:, 2]
            assert np.max(abs(balance)) < 1e-4
            absorbed = np.trapezoid(powers.sum(axis=1), [0, 60, 120, 180])
            assert abs(absorbed - trace["ledger"][-1, 0]) < 1e-4
            convective = np.trapezoid(trace["convection"], elapsed)
            radiative = np.trapezoid(trace["radiation"], elapsed)
            assert abs(absorbed - convective - radiative - stored[-1]) < 0.1
            assert abs(convective - record["metrics"]["convection_J"]) < 0.1
            assert abs(radiative - record["metrics"]["radiation_J"]) < 0.1
        margins = {"peak": 360 - derived["peak_K"], "spread": 12 - derived["max_spread_K"],
                   "final_low": derived["final_mean_K"] - 348, "final_high": 352 - derived["final_mean_K"]}
        violated = [name for name, value in margins.items() if value < -1e-5]
        assert violated == record["violated"]
        assert record["feasible_at_samples"] == (not violated)
        assert record["near_boundary"] == (min(abs(value) for value in margins.values()) <= 0.05)
    for group, counts in summary["groups"].items():
        subset = [record for record in records if record["group"] == group]
        assert counts["count"] == len(subset)
        assert counts["feasible"] == sum(record["feasible_at_samples"] for record in subset)
        assert counts["violations"] == {name: sum(name in record["violated"] for record in subset) for name in LIMITS}
    selected = select_refinements(records)
    assert len(refinements) == len({record["id"] for record in refinements}) == len(selected)
    assert sorted(record["id"] for record in refinements) == selected == summary["refined_cases"]
    for record in refinements:
        original = next(item for item in records if item["id"] == record["id"])
        for quantity in ["peak_K", "max_spread_K", "final_mean_K"]:
            difference = record["metrics"][quantity] - original["metrics"][quantity]
            assert abs(difference) < 0.01
            assert abs(difference - record["metric_changes"][quantity]) < 1e-12
        assert record["classification_changed"] == (record["violated"] != original["violated"])
    nominal = next(record for record in records if record["id"] == "nominal")
    previous = read_json(RADIATION / "results/experiment.json")["optimized"]
    for quantity in ["peak_K", "max_spread_K", "final_mean_K", "mse_K2"]:
        assert abs(nominal["metrics"][quantity] - previous[quantity]) < 1e-6
    scaling_checks = []
    with np.load(ROOT / nominal["trace"]) as nominal_trace:
        for case_id, scale in [("corner-000", 0.9), ("corner-031", 1.1)]:
            scaled = next(record for record in records if record["id"] == case_id)
            assert all(value == scale for value in scaled["factors"].values())
            with np.load(ROOT / scaled["trace"]) as trace:
                differences = {name: float(np.max(abs(trace[name] - nominal_trace[name])))
                               for name in ["mean", "std", "minimum", "maximum"]}
                assert max(differences.values()) < 1e-6
                ledger_difference = float(np.max(abs(trace["ledger"] - scale * nominal_trace["ledger"])))
                assert ledger_difference < 1e-5
            scaling_checks.append({"id": case_id, "common_scale": scale,
                                   "max_trace_differences_K": differences, "scaled_ledger_max_difference_J": ledger_difference})
    (results / "scaling-symmetry.json").write_text(json.dumps({
        "status": "PASS", "analysis": "Post-scan check using prespecified corners; no added or selected calibration data.",
        "explanation": "Common scaling of heat capacity, axial conduction, convection, emissivity and absorbed power cancels from the temperature ODE.",
        "checks": scaling_checks,
    }, indent=2) + "\n")
    print("PASS fixed protocol, model, command trajectory and 181-case design")
    print("PASS parameter isolation, actual/command power limits, all traces and reconstructed metrics")
    print("PASS energy conservation, independent time-integrated heat loss and exact absorbed energy")
    print(f"PASS {len(refinements)} selected refined cases; maximum temperature-metric difference <0.01K")
    print("PASS independently recounted violations; nominal reproduces previous fine-grid result")
    print("PASS common +/-10% parameter scaling leaves saved temperature traces unchanged within 1e-6K")
    labels = {
        "power_gain": "Absorbed-power gain", "convection": "Convection coefficient",
        "emissivity": "Emissivity", "heat_capacity": "Heat capacity", "axial_conductance": "Axial conduction",
    }
    figure, axes = plt.subplots(1, 3, figsize=(15, 4.8), constrained_layout=True)
    for factor in FACTORS:
        subset = sorted([record for record in records if record["group"] == "oat" and by_case[record["id"]]["factor"] == factor],
                        key=lambda record: record["factors"][factor])
        percentages = [-10, -5, 0, 5, 10]
        temperatures = [subset[0]["metrics"]["final_mean_K"], subset[1]["metrics"]["final_mean_K"],
                        nominal["metrics"]["final_mean_K"], subset[2]["metrics"]["final_mean_K"], subset[3]["metrics"]["final_mean_K"]]
        axes[0].plot(percentages, temperatures, "o-", label=labels[factor], markersize=4)
    axes[0].axhspan(348, 352, color="green", alpha=0.08)
    axes[0].axhline(348, color="black", linestyle="--", linewidth=0.7)
    axes[0].axhline(352, color="black", linestyle="--", linewidth=0.7)
    axes[0].set(title="One parameter at a time", xlabel="Parameter change (%)", ylabel="Final mean temperature (K)")
    axes[0].legend(fontsize=7)
    groups = ["oat", "corners", "sobol"]
    names = ["One-at-a-time\n20 cases", "Box corners\n32 cases", "Sobol interior\n128 cases"]
    failed = [summary["groups"][group]["count"] - summary["groups"][group]["feasible"] for group in groups]
    feasible = [summary["groups"][group]["feasible"] for group in groups]
    axes[1].bar(names, feasible, label="Feasible", color="#3d8563")
    axes[1].bar(names, failed, bottom=feasible, label="Violates a limit", color="#c26949")
    for index, (passed, rejected) in enumerate(zip(feasible, failed, strict=True)):
        axes[1].text(index, passed + rejected + 1, f"{rejected}/{passed + rejected} violate", ha="center", fontsize=8)
    axes[1].set(title="Counts in specified designs (not probabilities)", ylabel="Number of cases", ylim=(0, 146))
    axes[1].legend(fontsize=8)
    for label, case_id in [("Nominal", "nominal"), ("Lowest final mean", summary["lowest_final"]), ("Highest final mean", summary["highest_final"])]:
        record = next(item for item in records if item["id"] == case_id)
        with np.load(ROOT / record["trace"]) as trace:
            axes[2].plot(trace["time"], trace["mean"], label=label)
    elapsed = np.linspace(0, 180, 181)
    axes[2].plot(elapsed, target(elapsed), "k--", label="Target")
    axes[2].set(title="Identical commanded heating trajectory", xlabel="Time (s)", ylabel="Mean temperature (K)")
    axes[2].legend(fontsize=8)
    for axis in [axes[0], axes[2]]:
        axis.grid(alpha=0.2)
    figure.suptitle("Parameter mismatch sensitivity - synthetic +/-10% box, not equipment tolerances", fontsize=13)
    figure.savefig(results / "sensitivity.png", dpi=150)
    plt.close(figure)
    print("PASS results/sensitivity.png rendered")


if __name__ == "__main__":
    main()
