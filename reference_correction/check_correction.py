import json
from pathlib import Path

from correction import apply_offset, estimate_offset, np


def main():
    reference = np.full(10, 296.15)
    offsets = np.array([.4, -.3, .1])
    sensors = reference[:, None] + offsets
    before = sensors.copy()
    estimate = estimate_offset(sensors, reference)
    np.testing.assert_allclose(estimate["offset_K"], offsets, atol=1e-12)
    np.testing.assert_allclose(apply_offset(sensors, estimate["offset_K"]), np.full_like(sensors, 296.15), atol=1e-12)
    np.testing.assert_array_equal(sensors, before)
    shifted = estimate_offset(sensors, reference + .35)
    np.testing.assert_allclose(apply_offset(sensors, shifted["offset_K"]), np.full_like(sensors, 296.5), atol=1e-12)
    readings = np.array([[300., 301.], [300.2, 300.8], [299.8, 301.2]])
    actual = estimate_offset(readings, np.full(3, 300.))
    np.testing.assert_allclose(actual["mean_standard_error_K"], [.2 / np.sqrt(3)] * 2, atol=1e-12)
    rejected = 0
    invalid = [
        lambda: estimate_offset([[300, 300]], [300]),
        lambda: estimate_offset([[300, 300], [300, 300]], [300]),
        lambda: estimate_offset([[300, np.nan], [300, 300]], [300, 300]),
        lambda: estimate_offset([[300], [300]], [300, np.inf]),
        lambda: estimate_offset([[0], [300]], [300, 300]),
        lambda: estimate_offset([300, 300], [300, 300]),
        lambda: estimate_offset(np.empty((2, 0)), [300, 300]),
        lambda: apply_offset([[300, 300]], [1]),
        lambda: apply_offset([[300, 300]], [np.nan, 0]),
        lambda: apply_offset([[300, 300]], [301, 0]),
    ]
    for operation in invalid:
        try:
            operation()
        except ValueError:
            rejected += 1
        else:
            raise AssertionError("Invalid correction input was accepted")
    result = {"status": "PASS", "invalid_inputs_rejected": rejected,
              "checks": ["channel offsets", "non-mutating correction", "reference error transfer", "standard error arithmetic"]}
    root = Path(__file__).resolve().parent
    (root / "results").mkdir(exist_ok=True)
    (root / "results/correction-checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
