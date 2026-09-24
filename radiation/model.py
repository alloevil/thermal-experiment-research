import os
import time
from dataclasses import dataclass

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
from scipy.integrate import solve_ivp
from scipy.sparse import bmat, csr_matrix, diags
from scipy.special import erf


@dataclass(frozen=True)
class Parameters:
    length: float = 0.06
    mass: float = 0.004
    heat_capacity: float = 500.0
    surface_area: float = 0.0012
    axial_conductance: float = 0.0002
    convection: float = 10.0
    convection_variation: float = 0.3
    emissivity: float = 0.9
    sigma: float = 5.670374419e-8
    ambient: float = 296.15


class HeatingModel:
    def __init__(self, cells=24, parameters=None, radiation="full", uniform_heating=False):
        self.cells = cells
        self.parameters = parameters or Parameters()
        self.radiation = radiation
        if radiation not in {"full", "linear"}:
            raise ValueError("Unknown radiation model")
        params = self.parameters
        self.width = params.length / cells
        self.coordinates = (np.arange(cells) + 0.5) * self.width
        self.cell_capacity = params.mass * params.heat_capacity / cells
        self.cell_area = params.surface_area / cells
        self.convection = params.convection * (
            1 + params.convection_variation * np.cos(np.pi * self.coordinates / params.length)
        )
        diagonal = np.full(cells, -2.0)
        diagonal[[0, -1]] = -1.0
        self.conduction = diags(
            [np.ones(cells - 1), diagonal, np.ones(cells - 1)], [-1, 0, 1], format="csr"
        ) * (params.axial_conductance / self.width)
        edges = np.linspace(0, params.length, cells + 1)
        centers = params.length * np.array([0.15, 0.5, 0.85])
        cumulative = erf((edges[:, None] - centers) / (np.sqrt(2) * 0.15 * params.length))
        weights = np.diff(cumulative, axis=0)
        self.heater_weights = weights / weights.sum(axis=0)
        if uniform_heating:
            self.heater_weights[:] = 1 / cells
        assert np.allclose(self.heater_weights.sum(axis=0), 1)

    def losses(self, temperature):
        params = self.parameters
        convection = self.cell_area * self.convection * (temperature - params.ambient)
        if self.radiation == "full":
            radiation = self.cell_area * params.emissivity * params.sigma * (
                temperature**4 - params.ambient**4
            )
        else:
            radiation = self.cell_area * params.emissivity * params.sigma * (
                4 * params.ambient**3 * (temperature - params.ambient)
            )
        return convection, radiation

    def rhs(self, state, power):
        temperature = state[:self.cells]
        convection, radiation = self.losses(temperature)
        thermal_rate = (
            self.conduction @ temperature + self.heater_weights @ power - convection - radiation
        ) / self.cell_capacity
        return np.concatenate([thermal_rate, [np.sum(power), np.sum(convection), np.sum(radiation)]])

    def jacobian(self, temperature):
        params = self.parameters
        convection_gradient = self.cell_area * self.convection
        radiation_gradient = self.cell_area * params.emissivity * params.sigma * 4 * (
            temperature**3 if self.radiation == "full" else np.full(self.cells, params.ambient**3)
        )
        thermal = (self.conduction - diags(convection_gradient + radiation_gradient)) / self.cell_capacity
        ledger = csr_matrix(np.vstack([np.zeros(self.cells), convection_gradient, radiation_gradient]))
        return bmat([[thermal, csr_matrix((self.cells, 3))], [ledger, csr_matrix((3, 3))]], format="csc")

    def solve(self, powers, knots=None, sample_step=1.0, initial=None, rtol=1e-8, atol=1e-9):
        start = time.perf_counter()
        knots = np.asarray([0, 60, 120, 180] if knots is None else knots, dtype=float)
        powers = np.asarray(powers, dtype=float)
        if powers.shape != (len(knots), 3) or not np.isfinite(powers).all():
            raise ValueError("Expected finite power array with one row per knot and three zones")
        if not np.all(np.diff(knots) > 0) or sample_step <= 0:
            raise ValueError("Time must increase")
        temperature = np.full(self.cells, self.parameters.ambient) if initial is None else np.array(initial)
        state = np.concatenate([temperature, np.zeros(3)])
        saved_times, saved_states = [knots[0]], [state.copy()]
        evaluations = 0
        for segment in range(len(knots) - 1):
            left, right = knots[segment:segment + 2]
            def derivative(elapsed, current):
                fraction = (elapsed - left) / (right - left)
                power = powers[segment] * (1 - fraction) + powers[segment + 1] * fraction
                return self.rhs(current, power)
            times = np.linspace(left, right, int(np.ceil((right - left) / sample_step)) + 1)
            solution = solve_ivp(
                derivative, (left, right), state, method="BDF", t_eval=times,
                jac=lambda elapsed, current: self.jacobian(current[:self.cells]), rtol=rtol, atol=atol,
            )
            if not solution.success:
                raise RuntimeError(solution.message)
            saved_times.extend(solution.t[1:])
            saved_states.extend(solution.y[:, 1:].T)
            state = solution.y[:, -1]
            evaluations += solution.nfev
        states = np.asarray(saved_states)
        assert np.isfinite(states).all() and np.min(states[:, :self.cells]) > 0
        return {
            "time": np.asarray(saved_times), "temperature": states[:, :self.cells],
            "ledger": states[:, self.cells:], "initial": temperature,
            "wall_seconds": time.perf_counter() - start, "rhs_evaluations": evaluations,
        }


def target(time):
    return 296.15 + (350.0 - 296.15) * np.minimum(np.asarray(time) / 120.0, 1)


def metrics(model, result):
    temperature, elapsed = result["temperature"], result["time"]
    error = np.mean((temperature - target(elapsed)[:, None]) ** 2, axis=1)
    stored = model.cell_capacity * np.sum(temperature - result["initial"], axis=1)
    ledger = result["ledger"]
    balance = stored - (ledger[:, 0] - ledger[:, 1] - ledger[:, 2])
    return {
        "mse_K2": float(np.trapezoid(error, elapsed) / (elapsed[-1] - elapsed[0])),
        "peak_K": float(temperature.max()),
        "max_spread_K": float(np.ptp(temperature, axis=1).max()),
        "final_mean_K": float(temperature[-1].mean()),
        "final_std_K": float(temperature[-1].std()),
        "absorbed_J": float(ledger[-1, 0]), "convection_J": float(ledger[-1, 1]),
        "radiation_J": float(ledger[-1, 2]), "stored_J": float(stored[-1]),
        "max_balance_residual_J": float(np.max(np.abs(balance))),
        "wall_seconds": result["wall_seconds"], "rhs_evaluations": result["rhs_evaluations"],
    }
