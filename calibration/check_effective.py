import json
from dataclasses import replace
from pathlib import Path

from effective import CALIBRATION_KNOTS, CALIBRATION_POWERS, EffectiveModel, HeatingModel, Parameters, np


ROOT = Path(__file__).resolve().parent


def main():
    powers = CALIBRATION_POWERS
    physical = HeatingModel(cells=48)
    nominal = physical.solve(powers, knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-10, atol=1e-11)
    equivalent = EffectiveModel(np.ones(4), cells=48).solve(powers, knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-10, atol=1e-11)
    nominal_difference = float(np.max(abs(nominal["temperature"] - equivalent["temperature"])))
    assert nominal_difference < 1e-6
    factors = {"emissivity": 1.08, "convection": 0.96, "heat_capacity": 0.93, "power_gain": 1.04, "axial_conductance": 1.02}
    params = Parameters()
    modified = replace(params, **{name: getattr(params, name) * factor for name, factor in factors.items() if name != "power_gain"})
    physical_result = HeatingModel(cells=48, parameters=modified).solve(
        powers * factors["power_gain"], knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-10, atol=1e-11)
    ratios = np.array([factors[name] / factors["heat_capacity"] for name in ["axial_conductance", "convection", "emissivity", "power_gain"]])
    model = EffectiveModel(ratios, cells=48)
    effective_result = model.solve(powers, knots=CALIBRATION_KNOTS, sample_step=5, rtol=1e-10, atol=1e-11)
    equivalence_difference = float(np.max(abs(physical_result["temperature"] - effective_result["temperature"])))
    assert equivalence_difference < 1e-5
    ledger_difference = float(np.max(abs(physical_result["ledger"] / factors["heat_capacity"] - effective_result["ledger"])))
    assert ledger_difference < 1e-5
    state = np.concatenate([effective_result["temperature"][20], np.zeros(3)])
    direction = np.random.default_rng(20260925).normal(size=len(state))
    step = 1e-4
    numerical = (model.rhs(state + step * direction, powers[2]) - model.rhs(state - step * direction, powers[2])) / (2 * step)
    analytic = model.jacobian(state[:48]) @ direction
    jac_error = float(np.linalg.norm(numerical - analytic) / np.linalg.norm(analytic))
    assert jac_error < 1e-7
    result = {"status": "PASS", "nominal_max_difference_K": nominal_difference,
              "physical_equivalence_max_difference_K": equivalence_difference,
              "normalized_ledger_max_difference": ledger_difference, "jacobian_relative_error": jac_error,
              "physical_factors": factors, "equivalent_ratios": ratios.tolist()}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/model-checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
