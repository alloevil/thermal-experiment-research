import json
import os
import time
from pathlib import Path

from effective import EffectiveModel, metrics, np, sensor_prediction, temperature_margins
from scipy.optimize import Bounds, least_squares, minimize


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def append_call(path, value):
    with path.open("a") as output:
        output.write(json.dumps(value, allow_nan=False) + "\n")
        output.flush()
        os.fsync(output.fileno())


def fit_ratios(observed_times, observed_temperatures, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "fit.json"
    if destination.exists():
        return json.loads(destination.read_text())
    if (output_dir / "fit-calls.jsonl").exists():
        raise RuntimeError("Partial fit must be archived explicitly before restarting")
    start = time.perf_counter()
    call_count = 0
    def residual(ratios):
        nonlocal call_count
        elapsed, prediction = sensor_prediction(ratios)
        np.testing.assert_allclose(elapsed, observed_times, rtol=0, atol=0)
        residuals = (prediction - observed_temperatures) / 0.1
        call_count += 1
        append_call(output_dir / "fit-calls.jsonl", {
            "call": call_count, "ratios": ratios.tolist(), "residual_rmse_K": float(np.sqrt(np.mean(residuals**2)) * 0.1),
        })
        return residuals.ravel()
    result = least_squares(
        residual, np.ones(4), bounds=(np.full(4, 0.9 / 1.1), np.full(4, 1.1 / 0.9)),
        method="trf", jac="2-point", diff_step=1e-4, max_nfev=40,
        ftol=1e-7, xtol=1e-7, gtol=1e-7,
    )
    singular_values = np.linalg.svd(result.jac, compute_uv=False)
    normalized_jacobian = result.jac / np.linalg.norm(result.jac, axis=0)
    correlations = normalized_jacobian.T @ normalized_jacobian
    payload = {
        "ratios": result.x.tolist(), "success": bool(result.success), "status": int(result.status),
        "message": str(result.message), "scipy_nfev": int(result.nfev), "actual_solver_calls": call_count,
        "wall_seconds": time.perf_counter() - start, "train_rmse_K": float(np.sqrt(np.mean(result.fun**2)) * 0.1),
        "active_mask": result.active_mask.tolist(), "singular_values": singular_values.tolist(),
        "jacobian_condition": float(singular_values[0] / singular_values[-1]),
        "jacobian_column_cosines": correlations.tolist(),
    }
    np.savez_compressed(output_dir / "fit-diagnostics.npz", jacobian=result.jac, residuals=result.fun)
    write_json(destination, payload)
    return payload


def optimize_control(ratios, initial_powers, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "control.json"
    if destination.exists():
        return json.loads(destination.read_text())
    if (output_dir / "control-calls.jsonl").exists():
        raise RuntimeError("Partial control optimization must be archived before restarting")
    model = EffectiveModel(ratios, cells=24)
    cache = {}
    def powers(variables):
        return np.vstack([np.zeros(3), np.asarray(variables).reshape(3, 3)])
    def evaluate(variables):
        key = tuple(variables)
        if key not in cache:
            summary = metrics(model, model.solve(powers(variables), sample_step=1))
            cache[key] = summary
            append_call(output_dir / "control-calls.jsonl", {
                "call": len(cache), "variables": list(key), "metrics": summary,
            })
        return cache[key]
    def slew_margins(variables):
        slew = np.diff(powers(variables), axis=0) / 60
        return np.concatenate([(0.015 / 1.1 - slew).ravel(), (0.015 / 1.1 + slew).ravel()])
    def checkpoint(variables):
        write_json(output_dir / "control-checkpoint.json", {"powers": powers(variables).tolist(), "calls": len(cache)})
    start = time.perf_counter()
    result = minimize(
        lambda variables: evaluate(variables)["mse_K2"], np.array(initial_powers)[1:].ravel(),
        method="SLSQP", bounds=Bounds(np.zeros(9), np.full(9, 1 / 1.1)),
        constraints=[{"type": "ineq", "fun": lambda variables: temperature_margins(evaluate(variables))},
                     {"type": "ineq", "fun": slew_margins}],
        options={"maxiter": 40, "ftol": 1e-6, "eps": 1e-4}, callback=checkpoint,
    )
    payload = {"success": bool(result.success), "message": str(result.message), "iterations": int(result.nit),
               "actual_solver_calls": len(cache), "wall_seconds": time.perf_counter() - start,
               "powers": powers(result.x).tolist(), "predicted_mse_K2": float(result.fun)}
    write_json(destination, payload)
    return payload
