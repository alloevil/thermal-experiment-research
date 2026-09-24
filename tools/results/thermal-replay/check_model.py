import json
from dataclasses import replace
from pathlib import Path

from model import HeatingModel, Parameters, metrics, np


ROOT = Path(__file__).resolve().parent


def main():
    checks = {}
    model = HeatingModel()
    equilibrium = model.solve(np.zeros((4, 3)))
    checks["equilibrium_error_K"] = float(np.max(abs(equilibrium["temperature"] - model.parameters.ambient)))
    assert checks["equilibrium_error_K"] < 1e-7
    lossless = replace(Parameters(), convection=0, emissivity=0)
    model = HeatingModel(parameters=lossless, uniform_heating=True)
    heated = model.solve(np.full((2, 3), 0.1), knots=[0, 10])
    exact = lossless.ambient + 0.3 * heated["time"] / (lossless.mass * lossless.heat_capacity)
    checks["lossless_heating_error_K"] = float(np.max(abs(heated["temperature"] - exact[:, None])))
    assert checks["lossless_heating_error_K"] < 1e-5
    errors = []
    for cells in [16, 32, 64, 128]:
        model = HeatingModel(cells=cells, parameters=lossless)
        initial = lossless.ambient + 10 * np.cos(np.pi * model.coordinates / lossless.length)
        result = model.solve(np.zeros((2, 3)), knots=[0, 30], initial=initial, rtol=1e-11, atol=1e-12)
        diffusivity = lossless.axial_conductance * lossless.length / (lossless.mass * lossless.heat_capacity)
        exact = lossless.ambient + 10 * np.exp(-diffusivity * (np.pi / lossless.length)**2 * 30) * np.cos(np.pi * model.coordinates / lossless.length)
        errors.append(float(np.sqrt(np.mean((result["temperature"][-1] - exact)**2))))
    orders = (np.log(np.array(errors[:-1]) / errors[1:]) / np.log(2)).tolist()
    assert all(1.7 < order < 2.3 for order in orders), orders
    checks["diffusion_rmse_K"] = errors
    checks["diffusion_orders"] = orders
    powers = np.array([[0, 0, 0], [0.6, 0.5, 0.7], [0.8, 0.7, 0.6], [0.3, 0.4, 0.5]])
    results = {}
    for cells in [12, 24, 48, 96]:
        model = HeatingModel(cells)
        result = model.solve(powers, sample_step=0.25)
        summary = metrics(model, result)
        assert summary["max_balance_residual_J"] < 1e-4
        results[cells] = (result, summary)
        print(f"GRID {cells}: {json.dumps(summary)}", flush=True)
    differences = {}
    for coarse, fine in [(12, 24), (24, 48), (48, 96)]:
        coarse_field, fine_field = results[coarse][0]["temperature"], results[fine][0]["temperature"]
        differences[f"{coarse}-{fine}"] = {
            "mean_K": float(np.max(abs(coarse_field.mean(axis=1) - fine_field.mean(axis=1)))),
            "std_K": float(np.max(abs(coarse_field.std(axis=1) - fine_field.std(axis=1)))),
            "max_K": float(np.max(abs(coarse_field.max(axis=1) - fine_field.max(axis=1)))),
        }
    for quantity in ["mean_K", "std_K"]:
        assert differences["24-48"][quantity] < differences["12-24"][quantity]
        assert differences["48-96"][quantity] < 0.1
    model = HeatingModel(96)
    strict = model.solve(powers, sample_step=0.25, rtol=1e-10, atol=1e-11)
    checks["time_tolerance_difference_K"] = float(np.max(abs(strict["temperature"] - results[96][0]["temperature"])))
    assert checks["time_tolerance_difference_K"] < 0.001
    losses = [model.losses(temperature) for temperature in strict["temperature"]]
    integrated = np.trapezoid(np.array([[item.sum() for item in pair] for pair in losses]), strict["time"], axis=0)
    checks["independent_loss_integral_errors_J"] = (integrated - strict["ledger"][-1, 1:]).tolist()
    assert np.max(abs(integrated - strict["ledger"][-1, 1:])) < 0.1
    state = np.concatenate([strict["temperature"][200], np.zeros(3)])
    direction = np.random.default_rng(20260924).normal(size=len(state))
    step = 1e-4
    numerical = (model.rhs(state + step * direction, powers[1]) - model.rhs(state - step * direction, powers[1])) / (2 * step)
    analytic = model.jacobian(state[:96]) @ direction
    checks["jacobian_relative_error"] = float(np.linalg.norm(numerical - analytic) / np.linalg.norm(analytic))
    assert checks["jacobian_relative_error"] < 1e-7
    payload = {"status": "PASS", "checks": checks, "grid_differences": differences,
               "grid_metrics": {cells: pair[1] for cells, pair in results.items()}}
    (ROOT / "results/model-checks.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(payload, indent=2), flush=True)
    print("PASS equilibrium, analytic heating/diffusion, energy, mesh, time and Jacobian checks")


if __name__ == "__main__":
    main()
