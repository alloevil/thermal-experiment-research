import json
import os
from pathlib import Path

os.environ["MPLBACKEND"] = "Agg"

from effective import RATIO_NAMES, np
from model import target
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent


def main():
    results = ROOT / "results"
    cases = [json.loads((results / f"object-{object_index}/noise-{replicate}/case.json").read_text())
             for object_index in range(8) for replicate in range(2)]
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for case in cases:
        axes[0, 0].plot([0, 1], [case["prediction"]["nominal_rmse_K"], case["prediction"]["calibrated_rmse_K"]],
                        "o-", alpha=0.6, markersize=4, color="#226e9c")
    axes[0, 0].set(yscale="log", xticks=[0, 1], xticklabels=["Nominal model", "Calibrated ratios"],
                   ylabel="Held-out temperature RMSE (K)", title="Same held-out input, same hidden physical model")
    for case in cases:
        axes[0, 1].plot([0, 1], [case["nominal_physical"]["mse_K2"], case["calibrated_physical"]["mse_K2"]],
                        "o-", alpha=0.6, markersize=4, color="#387c4a")
    axes[0, 1].set(xticks=[0, 1], xticklabels=["Nominal reoptimization", "Calibrated reoptimization"],
                   ylabel="Physical-model tracking MSE (K²)", title="Matched optimizer settings; calibration costs extra")
    relative_errors = np.array([case["ratio_relative_errors"] for case in cases]) * 100
    axes[1, 0].boxplot(relative_errors, tick_labels=["Conduction/C", "Convection/C", "Radiation/C", "Gain/C"])
    axes[1, 0].axhline(0, color="black", linewidth=0.8)
    axes[1, 0].set(ylabel="Effective-ratio relative error (%)", title="Not estimates of absolute physical parameters")
    worst = max(cases, key=lambda case: case["nominal_physical"]["mse_K2"])
    folder = results / f"object-{worst['object']}"
    for label, path, color in [
        ("Nominal controller", folder / "nominal-physical.npz", "#a76124"),
        ("Calibrated controller", folder / "noise-0/calibrated-physical.npz", "#226e9c"),
    ]:
        with np.load(path) as data:
            elapsed, temperatures = data["time"], data["temperature"]
            axes[1, 1].plot(elapsed, temperatures.mean(axis=1), label=label, color=color)
            axes[1, 1].fill_between(elapsed, temperatures.min(axis=1), temperatures.max(axis=1), color=color, alpha=0.12)
    axes[1, 1].plot(elapsed, target(elapsed), "k--", label="Target")
    axes[1, 1].axhline(360, color="red", linewidth=0.8, label="Peak limit")
    axes[1, 1].set(xlabel="Time (s)", ylabel="Temperature (K)",
                   title=f"Largest nominal MSE: object {worst['object']}, noise 0")
    axes[1, 1].legend(fontsize=8)
    for axis in axes.flat:
        axis.grid(alpha=0.2)
    figure.suptitle("Effective-ratio calibration: 8 synthetic objects x 2 noise realizations; no hardware validation", fontsize=12)
    figure.savefig(results / "calibration-results.png", dpi=150)
    plt.close(figure)
    print("PASS results/calibration-results.png rendered")


if __name__ == "__main__":
    main()
