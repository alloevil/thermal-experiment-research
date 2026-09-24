import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radiation"))

from model import HeatingModel, Parameters, metrics, np
from scipy.sparse import bmat, csr_matrix, diags


RATIO_NAMES = ["conduction_per_capacity", "convection_per_capacity", "radiation_per_capacity", "gain_per_capacity"]
CALIBRATION_KNOTS = np.arange(0, 241, 40, dtype=float)
CALIBRATION_POWERS = np.array([
    [0, 0, 0], [0.4, 0.1, 0.1], [0.1, 0.4, 0.1], [0.1, 0.1, 0.4],
    [0.4, 0.4, 0.4], [0.2, 0.2, 0.2], [0, 0, 0],
])
SENSOR_POSITIONS = Parameters().length * np.array([0.15, 0.5, 0.85])


class EffectiveModel(HeatingModel):
    def __init__(self, ratios, cells=48):
        super().__init__(cells=cells)
        self.ratios = np.asarray(ratios, dtype=float)
        if self.ratios.shape != (4,) or not np.isfinite(self.ratios).all() or np.any(self.ratios <= 0):
            raise ValueError("Four positive finite effective ratios required")
        self.conduction = self.conduction * self.ratios[0]
        self.convection = self.convection * self.ratios[1]

    def losses(self, temperature):
        convection, radiation = super().losses(temperature)
        return convection, radiation * self.ratios[2]

    def jacobian(self, temperature):
        params = self.parameters
        convection_gradient = self.cell_area * self.convection
        radiation_gradient = self.cell_area * params.emissivity * params.sigma * 4 * temperature**3 * self.ratios[2]
        thermal = (self.conduction - diags(convection_gradient + radiation_gradient)) / self.cell_capacity
        ledger = csr_matrix(np.vstack([np.zeros(self.cells), convection_gradient, radiation_gradient]))
        return bmat([[thermal, csr_matrix((self.cells, 3))], [ledger, csr_matrix((3, 3))]], format="csc")

    def solve(self, powers, **kwargs):
        return super().solve(np.asarray(powers) * self.ratios[3], **kwargs)


def sensor_values(model, result):
    return np.array([np.interp(SENSOR_POSITIONS, model.coordinates, field) for field in result["temperature"]])


def sensor_prediction(ratios, powers=CALIBRATION_POWERS, knots=CALIBRATION_KNOTS, cells=48):
    model = EffectiveModel(ratios, cells=cells)
    result = model.solve(powers, knots=knots, sample_step=5, rtol=1e-9, atol=1e-10)
    return result["time"][1:], sensor_values(model, result)[1:]


def input_feasible(powers, gain=1.0):
    actual = np.asarray(powers) * gain
    return bool(actual.min() >= -1e-9 and actual.max() <= 1 + 1e-9
                and np.max(abs(np.diff(actual, axis=0) / 60)) <= 0.015 + 1e-9)


def temperature_margins(summary):
    return np.array([360 - summary["peak_K"], 12 - summary["max_spread_K"],
                     summary["final_mean_K"] - 348, 352 - summary["final_mean_K"]])
