import hashlib
import json
import os
from pathlib import Path

os.environ["MPLBACKEND"] = "Agg"

from model import HeatingModel, metrics, np, target
from experiment import BASELINE, KNOTS, input_margins, temperature_margins
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent


def main():
    protocol_hash = hashlib.sha256((ROOT / "protocol.md").read_bytes()).hexdigest()
    assert protocol_hash == (ROOT / "results/protocol-sha256.txt").read_text().strip()
    for record in json.loads((ROOT / "sources/manifest.json").read_text()):
        assert hashlib.sha256((ROOT / record["file"]).read_bytes()).hexdigest() == record["sha256"]
    print("PASS preregistered protocol and public source hashes")
    checks = json.loads((ROOT / "results/model-checks.json").read_text())
    assert checks["status"] == "PASS"
    experiment = json.loads((ROOT / "results/experiment.json").read_text())
    assert experiment["optimizer_success"]
    calls = [json.loads(line) for line in (ROOT / "results/optimization-calls.jsonl").read_text().splitlines()]
    assert len(calls) == experiment["optimization_solver_calls"]
    assert [record["call"] for record in calls] == list(range(1, len(calls) + 1))
    powers = np.array(experiment["optimized_powers_W"])
    assert input_margins(powers).min() >= -1e-9
    print(f"PASS optimizer call ledger: {len(calls)} calls; power/ramp constraints")
    results = {}
    balance_checks = {}
    for label, field in [("baseline", "baseline"), ("optimized", "optimized"), ("linear-radiation", "linear_radiation")]:
        loaded = np.load(ROOT / f"results/{label}.npz", allow_pickle=False)
        result = {key: loaded[key] for key in loaded.files}
        model = HeatingModel(96, radiation="linear" if label == "linear-radiation" else "full")
        actual = metrics(model, result)
        for key, value in actual.items():
            assert np.isclose(value, experiment[field][key], rtol=1e-10, atol=1e-10), (label, key)
        assert len(result["time"]) == 721 and np.max(np.diff(result["time"])) <= 0.25 + 1e-9
        exact_absorbed = np.trapezoid(result["powers"].sum(axis=1), KNOTS)
        assert abs(actual["absorbed_J"] - exact_absorbed) < 1e-4
        convection, radiation = [], []
        for temperature in result["temperature"]:
            convective, radiative = model.losses(temperature)
            convection.append(convective.sum())
            radiation.append(radiative.sum())
        independent_stored = exact_absorbed - np.trapezoid(convection, result["time"]) - np.trapezoid(radiation, result["time"])
        residual = float(independent_stored - actual["stored_J"])
        assert abs(residual) < 0.1
        balance_checks[label] = {"exact_absorbed_J": float(exact_absorbed), "external_quadrature_residual_J": residual}
        results[label] = result
    assert temperature_margins(experiment["optimized"]).min() > 0
    assert temperature_margins(experiment["baseline"]).min() < 0
    print("PASS saved field metrics, exact absorbed energy and independent loss quadrature")
    print("PASS optimized 96-cell/0.25s sampled temperature constraints; baseline fails as reported")
    max_difference = float(np.max(abs(results["linear-radiation"]["temperature"] - results["optimized"]["temperature"])))
    assert np.isclose(max_difference, experiment["radiation_comparison"]["max_temperature_difference_K"])
    assert np.array_equal(results["linear-radiation"]["powers"], results["optimized"]["powers"])
    print("PASS radiation-only comparison uses identical absorbed powers")
    fine_model = HeatingModel(96)
    denser = fine_model.solve(powers, sample_step=0.0625, rtol=1e-10, atol=1e-11)
    denser_metrics = metrics(fine_model, denser)
    assert temperature_margins(denser_metrics).min() > 0
    differences = {key: denser_metrics[key] - experiment["optimized"][key]
                   for key in ["mse_K2", "peak_K", "max_spread_K", "final_mean_K"]}
    assert abs(differences["peak_K"]) < 0.001 and abs(differences["max_spread_K"]) < 0.001
    print("PASS post-run 0.0625s sampling sensitivity; still not continuous-time certification")
    audit = {"status": "PASS", "energy_checks": balance_checks,
             "extra_sampling_check": {"step_s": 0.0625, "metrics": denser_metrics, "differences": differences}}
    (ROOT / "results/verification.json").write_text(json.dumps(audit, indent=2) + "\n")
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    elapsed = results["optimized"]["time"]
    axes[0, 0].plot(elapsed, target(elapsed), "k--", label="Target")
    for label, color in [("baseline", "#a65d21"), ("optimized", "#176ca4")]:
        temperature = results[label]["temperature"]
        axes[0, 0].plot(elapsed, temperature.mean(axis=1), color=color, label=label)
        axes[0, 0].fill_between(elapsed, temperature.min(axis=1), temperature.max(axis=1), color=color, alpha=0.15)
    axes[0, 0].axhline(360, color="red", linewidth=0.8, label="Peak limit")
    axes[0, 0].set(title="Mean temperature + spatial min/max", xlabel="Time (s)", ylabel="Temperature (K)")
    axes[0, 0].legend(fontsize=8)
    for zone in range(3):
        axes[0, 1].plot(KNOTS, powers[:, zone], "o-", label=f"Zone {zone + 1}")
    axes[0, 1].plot(KNOTS, BASELINE[:, 0], "k--", label="Baseline, each zone")
    axes[0, 1].set(title="Bounded absorbed power (not electrical power)", xlabel="Time (s)", ylabel="Power (W)", ylim=(0, 1.05))
    axes[0, 1].legend(fontsize=8)
    temperature = results["optimized"]["temperature"]
    image = axes[1, 0].imshow(temperature.T, aspect="auto", origin="lower", extent=[0, 180, 0, 60], cmap="inferno")
    axes[1, 0].set(title="Optimized temperature field", xlabel="Time (s)", ylabel="Position (mm)")
    figure.colorbar(image, ax=axes[1, 0], label="K")
    difference = results["linear-radiation"]["temperature"] - temperature
    axes[1, 1].plot(elapsed, difference.mean(axis=1), color="#68429a", label="Mean difference")
    axes[1, 1].fill_between(elapsed, difference.min(axis=1), difference.max(axis=1), color="#68429a", alpha=0.2)
    axes[1, 1].set(title="Linearized minus full radiation, identical input", xlabel="Time (s)", ylabel="Temperature difference (K)")
    axes[1, 1].legend(fontsize=8)
    for axis in [axes[0, 0], axes[0, 1], axes[1, 1]]:
        axis.grid(alpha=0.2)
    figure.suptitle("Three-zone heating with radiation - synthetic research model, NOT industrial validation", fontsize=12)
    figure.savefig(ROOT / "results/heating-results.png", dpi=150)
    plt.close(figure)
    print("PASS results/heating-results.png rendered")


if __name__ == "__main__":
    main()
