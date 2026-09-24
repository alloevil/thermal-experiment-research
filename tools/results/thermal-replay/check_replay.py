"""Verify newly computed arrays; no imports from the simulation implementation."""

import argparse
import json
from pathlib import Path

import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(actual, expected, label, tolerance=1e-8):
    require(np.isfinite(actual) and np.isfinite(expected) and abs(actual - expected) <= tolerance,
            f"Mismatch: {label}: {actual} vs {expected}")


def verify(directory):
    report = json.loads((directory / "results/experiment.json").read_text())
    reference = json.loads((directory / "reference-experiment.json").read_text())
    checks = json.loads((directory / "results/model-checks.json").read_text())
    require(checks["status"] == "PASS", "Original numerical checks did not pass")
    require(checks["checks"]["equilibrium_error_K"] < 1e-7, "Equilibrium error")
    require(checks["checks"]["lossless_heating_error_K"] < 1e-5, "Analytic heating error")
    require(all(1.7 < value < 2.3 for value in checks["checks"]["diffusion_orders"]), "Spatial convergence")
    require(checks["checks"]["time_tolerance_difference_K"] < .001, "Time convergence")
    require(checks["checks"]["jacobian_relative_error"] < 1e-7, "Jacobian check")
    require(report["optimizer_success"] is True, "Optimizer did not converge")
    require(report["iterations"] <= 40, "Optimization budget exceeded")
    calls = [json.loads(line) for line in (directory / "results/optimization-calls.jsonl").read_text().splitlines()]
    require([item["call"] for item in calls] == list(range(1, report["optimization_solver_calls"] + 1)), "Call ledger mismatch")
    energy_records, differences = {}, {}
    for name, key in [("baseline", "baseline"), ("optimized", "optimized"), ("linear-radiation", "linear_radiation")]:
        with np.load(directory / f"results/{name}.npz", allow_pickle=False) as data:
            times, field, powers = data["time"], data["temperature"], data["powers"]
            require(field.shape == (721, 96) and times.shape == (721,), "Wrong evaluation shape")
            require(np.isfinite(field).all() and field.min() > 0, "Invalid temperature")
            require(np.array_equal(times, np.arange(721) * .25), "Wrong evaluation times")
            require(powers.shape == (4, 3) and np.isfinite(powers).all(), "Invalid power shape")
            require(powers.min() >= -1e-9 and powers.max() <= 1 + 1e-9, "Power violation")
            require(np.max(abs(np.diff(powers, axis=0) / 60)) <= .015 + 1e-9, "Power slope violation")
            require(np.all(powers[0] == 0), "Nonzero initial input")
            target = 296.15 + (350 - 296.15) * np.minimum(times / 120, 1)
            measured = {
                "mse_K2": float(np.trapezoid(np.mean((field - target[:, None])**2, axis=1), times) / 180),
                "peak_K": float(field.max()), "max_spread_K": float(np.ptp(field, axis=1).max()),
                "final_mean_K": float(field[-1].mean()), "final_std_K": float(field[-1].std()),
            }
            for quantity, value in measured.items():
                close(value, report[key][quantity], f"{name}/{quantity}")
            feasible = measured["peak_K"] <= 360 + 1e-5 and measured["max_spread_K"] <= 12 + 1e-5 and 348 - 1e-5 <= measured["final_mean_K"] <= 352 + 1e-5
            require(report[key]["feasible_at_sampled_points"] == feasible, "Feasibility label mismatch")
            require(feasible == (name == "optimized"), "Expected reproduced baseline/optimized/linear behavior changed")
            positions = (.5 + np.arange(96)) * .06 / 96
            convection = .0012 / 96 * 10 * (1 + .3 * np.cos(np.pi * positions / .06)) * (field - 296.15)
            radiation = .0012 / 96 * .9 * 5.670374419e-8 * (
                4 * 296.15**3 * (field - 296.15) if name == "linear-radiation" else field**4 - 296.15**4)
            absorbed = float(np.trapezoid(powers.sum(axis=1), [0, 60, 120, 180]))
            loss = float(np.trapezoid((convection + radiation).sum(axis=1), times))
            stored = .004 * 500 * (field.mean(axis=1) - 296.15)
            ledger = data["ledger"]
            require(ledger.shape == (721, 3) and np.isfinite(ledger).all(), "Invalid energy ledger")
            require(np.max(abs(stored - ledger[:, 0] + ledger[:, 1] + ledger[:, 2])) < 1e-4, "Energy conservation failure")
            close(absorbed, report[key]["absorbed_J"], "Absorbed energy", 1e-4)
            require(abs(absorbed - loss - stored[-1]) < .1, "Independent energy integral failure")
            energy_records[name] = {"absorbed_J": absorbed, "independent_balance_J": float(absorbed - loss - stored[-1])}
            differences[name] = {}
            for quantity in ["mse_K2", "peak_K", "max_spread_K", "final_mean_K"]:
                delta = measured[quantity] - reference[key][quantity]
                require(abs(delta) < (.02 if quantity == "mse_K2" else .01), f"Reference divergence: {name}/{quantity}")
                differences[name][quantity] = delta
    with np.load(directory / "results/optimized.npz") as full, np.load(directory / "results/linear-radiation.npz") as linear:
        require(np.array_equal(full["powers"], linear["powers"]), "Radiation comparison changed power")
    return {"status": "PASS", "new_optimizer_iterations": report["iterations"],
            "new_solver_calls": report["optimization_solver_calls"], "optimization_wall_seconds": report["optimization_wall_seconds"],
            "optimized": {name: report["optimized"][name] for name in ["mse_K2", "peak_K", "max_spread_K", "final_mean_K"]},
            "reference_differences": differences, "independent_energy_checks": energy_records,
            "scope": "New same-platform ODE and optimization replay, not new physics validation or algorithm comparison."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    (args.directory / "results/replay-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
