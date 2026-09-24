"""Optional demonstration plot; CLI functionality only needs NumPy and SciPy."""

import json
import os
from pathlib import Path

os.environ["MPLBACKEND"] = "Agg"
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    folder = ROOT / "demo"
    recommendation = json.loads((folder / "recommendation.json").read_text())
    posterior = json.loads((folder / "updated-posterior.json").read_text())
    measurement = json.loads((folder / "measurement.json").read_text())
    options = recommendation["options"]
    selected = next(item for item in options if item["experiment"] == recommendation["recommendation"])
    figure, axes = plt.subplots(1, 3, figsize=(13, 4.4), constrained_layout=True)
    names = ["convection", "offset"]
    positions = np.arange(2)
    axes[0].bar(positions - .18, [recommendation["posterior"]["model_probability"][name] for name in names], width=.36, label="Before next test")
    axes[0].bar(positions + .18, [posterior["model_probability"][name] for name in names], width=.36, label="After observed test")
    axes[0].set(xticks=positions, xticklabels=["Convection change", "Sensor offset"], ylim=(0, 1.1), ylabel="Relative probability in candidate set", title="An ambiguous initial record")
    axes[0].legend(fontsize=8)
    axes[1].bar([item["experiment"] for item in options], [item["expected_information_gain_nats"] for item in options],
                yerr=[item["monte_carlo_standard_error_nats"] for item in options], color="#42799a", capsize=4)
    axes[1].set(title="Pick one allowed experiment", ylabel="Estimated information gain (nats)")
    times = [item["time_s"] for item in selected["details"]["observations"]]
    for name in names:
        predicted = selected["predictions"][name]
        axes[2].plot(times, predicted["mean_K"], "o-", label=name)
        axes[2].fill_between(times, predicted["predictive_p05_K"], predicted["predictive_p95_K"], alpha=.15)
    axes[2].scatter(times, measurement["values_K"], marker="x", color="black", s=65, label="New measurement")
    axes[2].set(xlabel="Time (s)", ylabel="Sensor reading (K)", title=f"Execute simulated {selected['experiment']} and update")
    axes[2].legend(fontsize=8)
    for axis in axes:
        axis.grid(axis="y", alpha=.2)
    figure.suptitle("Next-experiment prototype: finite candidate models, not proven root cause or device safety", fontsize=12)
    figure.savefig(folder / "decision.png", dpi=150)
    print("PASS demo/decision.png rendered")


if __name__ == "__main__":
    main()
