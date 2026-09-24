import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

from model import HeatingModel, metrics, np
from scipy.optimize import Bounds, minimize


ROOT = Path(__file__).resolve().parent
KNOTS = np.array([0, 60, 120, 180])
BASELINE = np.tile(np.array([0, 0.7, 0.7, 0.4])[:, None], (1, 3))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def powers_from_variables(variables):
    return np.vstack([np.zeros(3), np.asarray(variables).reshape(3, 3)])


def temperature_margins(summary):
    return np.array([
        360 - summary["peak_K"], 12 - summary["max_spread_K"],
        summary["final_mean_K"] - 348, 352 - summary["final_mean_K"],
    ])


def input_margins(powers):
    differences = np.diff(powers, axis=0) / np.diff(KNOTS)[:, None]
    return np.concatenate([powers.ravel(), (1 - powers).ravel(),
                           (0.015 - differences).ravel(), (0.015 + differences).ravel()])


def assessment(model, powers, label):
    result = model.solve(powers, sample_step=0.25, rtol=1e-10, atol=1e-11)
    summary = metrics(model, result)
    summary["input_margins"] = input_margins(powers).tolist()
    summary["temperature_margins_K"] = temperature_margins(summary).tolist()
    summary["feasible_at_sampled_points"] = bool(
        min(summary["input_margins"]) >= -1e-9 and min(summary["temperature_margins_K"]) >= -1e-5
    )
    assert summary["max_balance_residual_J"] < 1e-4
    np.savez(ROOT / f"results/{label}.npz", **result, powers=powers, coordinates=model.coordinates)
    return result, summary


def main():
    if (ROOT / "results/experiment.json").exists():
        raise RuntimeError("Archive prior experiment outputs before a fresh optimization")
    protocol_hash = hashlib.sha256((ROOT / "protocol.md").read_bytes()).hexdigest()
    assert protocol_hash == (ROOT / "results/protocol-sha256.txt").read_text().strip()
    assert json.loads((ROOT / "results/model-checks.json").read_text())["status"] == "PASS"
    model = HeatingModel(24)
    write_json(ROOT / "results/experiment-config.json", {
        "parameters": asdict(model.parameters), "knots": KNOTS.tolist(),
        "initial_powers": BASELINE.tolist(), "optimizer": "SLSQP",
        "maxiter": 40, "ftol": 1e-6, "finite_difference_step": 1e-4,
        "optimization_cells": 24, "verification_cells": 96,
        "optimization_sample_step_s": 1, "verification_sample_step_s": 0.25,
        "protocol_sha256": protocol_hash,
    })
    cache = {}
    history_path = ROOT / "results/optimization-calls.jsonl"
    if history_path.exists():
        raise RuntimeError("Partial optimization exists; archive it explicitly before restarting")
    def evaluate(variables):
        key = tuple(variables)
        if key not in cache:
            summary = metrics(model, model.solve(powers_from_variables(variables)))
            cache[key] = summary
            with history_path.open("a") as output:
                output.write(json.dumps({"call": len(cache), "variables": list(key), "metrics": summary}) + "\n")
                output.flush()
            if len(cache) % 25 == 0:
                print(f"EVALUATIONS {len(cache)} mse={summary['mse_K2']:.5f}", flush=True)
        return cache[key]
    def iteration(variables):
        summary = evaluate(variables)
        write_json(ROOT / "results/optimizer-checkpoint.json", {
            "variables": variables.tolist(), "metrics": summary, "evaluations": len(cache),
        })
        print(f"ITERATE mse={summary['mse_K2']:.5f} margins={temperature_margins(summary)}", flush=True)
    start = time.perf_counter()
    solution = minimize(
        lambda variables: evaluate(variables)["mse_K2"], BASELINE[1:].ravel(),
        method="SLSQP", bounds=Bounds(np.zeros(9), np.ones(9)),
        constraints=[
            {"type": "ineq", "fun": lambda variables: temperature_margins(evaluate(variables))},
            {"type": "ineq", "fun": lambda variables: input_margins(powers_from_variables(variables))},
        ],
        options={"maxiter": 40, "ftol": 1e-6, "eps": 1e-4, "disp": True}, callback=iteration,
    )
    optimization_seconds = time.perf_counter() - start
    optimized = powers_from_variables(solution.x)
    write_json(ROOT / "results/optimizer-result.json", {
        "success": bool(solution.success), "message": str(solution.message),
        "iterations": int(solution.nit), "solver_calls": len(cache), "wall_seconds": optimization_seconds,
        "powers": optimized.tolist(), "objective_K2": float(solution.fun),
    })
    fine = HeatingModel(96)
    baseline_result, baseline_metrics = assessment(fine, BASELINE, "baseline")
    optimized_result, optimized_metrics = assessment(fine, optimized, "optimized")
    linear_result, linear_metrics = assessment(HeatingModel(96, radiation="linear"), optimized, "linear-radiation")
    margins = temperature_margins(optimized_metrics)
    experiment = {
        "status": "COMPLETED", "optimizer_success": bool(solution.success),
        "optimizer_message": str(solution.message), "iterations": int(solution.nit),
        "optimization_wall_seconds": optimization_seconds, "optimization_solver_calls": len(cache),
        "baseline": baseline_metrics, "optimized": optimized_metrics,
        "optimized_powers_W": optimized.tolist(),
        "mse_reduction_fraction": 1 - optimized_metrics["mse_K2"] / baseline_metrics["mse_K2"],
        "linear_radiation": linear_metrics,
        "radiation_comparison": {
            "max_temperature_difference_K": float(np.max(abs(linear_result["temperature"] - optimized_result["temperature"]))),
            "final_mean_difference_K": linear_metrics["final_mean_K"] - optimized_metrics["final_mean_K"],
            "radiation_energy_difference_J": linear_metrics["radiation_J"] - optimized_metrics["radiation_J"],
        },
        "optimization_to_fine_mse_difference_K2": optimized_metrics["mse_K2"] - float(solution.fun),
        "minimum_fine_temperature_margin_K": float(margins.min()),
        "limitations": [
            "One synthetic task, one prescribed initial guess, classical optimizer, no global optimality claim.",
            "Baseline is an unoptimized reference trajectory, not tuned PID/MPC or an equal-budget optimizer.",
            "Feasibility is checked on 96 cells at 0.25s samples, not a continuous-space/time certificate.",
            "This is mathematical verification, not an industrial or hardware validation.",
        ],
    }
    write_json(ROOT / "results/experiment.json", experiment)
    print(json.dumps(experiment, indent=2), flush=True)


if __name__ == "__main__":
    main()
