import numpy as np


def temperature_array(value, dimensions, name):
    array = np.asarray(value, dtype=float)
    if array.ndim != dimensions or not array.size or not np.isfinite(array).all() or np.any(array <= 0):
        raise ValueError(f"{name} must contain finite positive Kelvin readings with {dimensions} dimensions")
    return array


def estimate_offset(sensor_readings_K, reference_readings_K):
    sensors = temperature_array(sensor_readings_K, 2, "sensors")
    reference = temperature_array(reference_readings_K, 1, "reference")
    if sensors.shape[0] != reference.shape[0] or len(reference) < 2:
        raise ValueError("At least two synchronized reference/sensor observations are required")
    differences = sensors - reference[:, None]
    deviation = differences.std(axis=0, ddof=1)
    return {
        "offset_K": differences.mean(axis=0).tolist(), "samples": len(reference),
        "difference_sample_std_K": deviation.tolist(),
        "mean_standard_error_K": (deviation / np.sqrt(len(reference))).tolist(),
        "scope": "One-point offset only; standard errors exclude reference systematic error and sensor drift.",
    }


def apply_offset(readings_K, offset_K):
    readings = temperature_array(readings_K, 2, "readings")
    offset = np.asarray(offset_K, dtype=float)
    if offset.shape != (readings.shape[1],) or not np.isfinite(offset).all():
        raise ValueError("One finite offset per sensor channel is required")
    corrected = readings - offset
    if not np.isfinite(corrected).all() or np.any(corrected <= 0):
        raise ValueError("Corrected absolute temperatures must remain positive and finite")
    return corrected
