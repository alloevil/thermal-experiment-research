"""Adaptation of APMonitor's TCLab energy equations; see ATTRIBUTION.md and upstream/LICENSE.

Adds validation, an explicit coupling switch and interval-wise DOP853 integration.
Unlike the original script, this module never reads measurement targets during rollout.
"""

import csv
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parent
INITIAL = np.array([10., .01, .0075])
LOWER = np.array([2., .005, .002])
UPPER = np.array([20., .020, .015])
SCALE = np.array([1., 1000., 1000.])
CAPACITY_J_K = .004 * 500
AMBIENT_C = 23.
AREA = .001
EXCHANGE_AREA = .0002
EMISSIVITY = .9
SIGMA = 5.67e-8


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_data(path=ROOT / "upstream/data.txt"):
    with Path(path).open(newline="") as source:
        rows = list(csv.reader(source))
    expected = ['Time (sec)', 'Heater 1 (%)', 'Heater 2 (%)', 'Temperature 1 (degC)',
                'Temperature 2 (degC)', 'Set Point 1 (degC)', 'Set Point 2 (degC)']
    require([value.strip() for value in rows[0]] == expected, "Unexpected columns or units")
    data = np.asarray([[float(value) for value in row] for row in rows[1:] if row], dtype=float)
    require(data.ndim == 2 and data.shape[1] == 7 and len(data) >= 2, "Expected seven numeric columns")
    require(np.isfinite(data).all(), "Missing or nonfinite data")
    require(data[0, 0] == 0 and np.all(np.diff(data[:, 0]) > 0), "Time must increase strictly from zero")
    require(np.all((data[:, 1:3] >= 0) & (data[:, 1:3] <= 100)), "Heater input must be percent, 0–100")
    require(np.all(data[:, 3:5] > -273.15), "Invalid absolute temperature")
    return data


def fluxes(temperature_C, inputs_percent, parameters, coupled=True):
    temperature_K = np.asarray(temperature_C) + 273.15
    ambient_K = AMBIENT_C + 273.15
    transfer, alpha_one, alpha_two = parameters
    absorbed = np.array([alpha_one, alpha_two]) * inputs_percent
    convective = transfer * AREA * (temperature_K - ambient_K)
    radiative = EMISSIVITY * SIGMA * AREA * (temperature_K**4 - ambient_K**4)
    exchange = (transfer * EXCHANGE_AREA * (temperature_K[1] - temperature_K[0])
                + EMISSIVITY * SIGMA * EXCHANGE_AREA * (temperature_K[1]**4 - temperature_K[0]**4)) if coupled else 0.
    net = absorbed - convective - radiative + np.array([exchange, -exchange])
    return net, absorbed, convective, radiative


def rollout(times, inputs, initial_C, parameters, coupled=True, tolerance_scale=1., ledger=False):
    times, inputs = np.asarray(times, float), np.asarray(inputs, float)
    initial_C, parameters = np.asarray(initial_C, float), np.asarray(parameters, float)
    require(times.ndim == 1 and len(times) >= 2 and np.isfinite(times).all() and np.all(np.diff(times) > 0), "Invalid times")
    require(inputs.shape == (len(times), 2) and np.isfinite(inputs).all() and np.all((inputs >= 0) & (inputs <= 100)), "Invalid input sequence")
    require(initial_C.shape == (2,) and np.isfinite(initial_C).all() and np.all(initial_C > -273.15), "Invalid initial temperature")
    require(parameters.shape == (3,) and np.isfinite(parameters).all() and np.all(parameters > 0), "Invalid parameters")
    require(np.isfinite(tolerance_scale) and tolerance_scale > 0, "Invalid tolerance")
    state = np.concatenate([initial_C, np.zeros(3)]) if ledger else initial_C.copy()
    states = [state.copy()]
    evaluations = 0
    for index in range(len(times) - 1):
        applied = inputs[index]

        def derivative(elapsed, current):
            net, absorbed, convection, radiation = fluxes(current[:2], applied, parameters, coupled)
            rate = net / CAPACITY_J_K
            return np.concatenate([rate, [absorbed.sum(), convection.sum(), radiation.sum()]]) if ledger else rate

        solution = solve_ivp(derivative, (times[index], times[index + 1]), state,
                             method="DOP853", rtol=1e-8 * tolerance_scale, atol=1e-9 * tolerance_scale,
                             t_eval=[times[index + 1]])
        require(solution.success, solution.message)
        state = solution.y[:, -1]
        require(np.isfinite(state).all() and np.all(state[:2] > -273.15), "Invalid solver output")
        states.append(state.copy())
        evaluations += solution.nfev
    states = np.asarray(states)
    return {"temperature_C": states[:, :2], "ledger_J": states[:, 2:] if ledger else None,
            "rhs_evaluations": evaluations}


def error_metrics(prediction_C, measured_C):
    residual = prediction_C - measured_C
    return {"rmse_C": float(np.sqrt(np.mean(residual**2))),
            "rmse_per_channel_C": np.sqrt(np.mean(residual**2, axis=0)).tolist(),
            "mae_C": float(np.mean(abs(residual))), "mae_per_channel_C": np.mean(abs(residual), axis=0).tolist(),
            "relative_celsius_SSE": float(np.sum((residual / measured_C)**2))}
