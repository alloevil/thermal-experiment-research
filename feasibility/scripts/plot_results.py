import json
import os
from pathlib import Path


os.environ["MPLBACKEND"] = "Agg"

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import NullFormatter


ROOT = Path(__file__).resolve().parents[1]


def main():
    records = [json.loads(line) for line in (ROOT / "results/thermal-raw.jsonl").read_text().splitlines()]
    summary = json.loads((ROOT / "results/thermal-summary.json").read_text())
    resolutions = [16, 32, 64, 128]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.4), constrained_layout=True)
    timings = [[item["wall_seconds"] for item in records if item["resolution"] == resolution]
               for resolution in resolutions]
    axes[0].boxplot(timings, tick_labels=[f"{resolution}x{resolution}" for resolution in resolutions])
    axes[0].set(xlabel="Grid", ylabel="Wall time per solve (s)", title="8 matched inputs x 5 repeats per grid")
    for case_index in range(8):
        errors = [next(item["rmse_K"] for item in records
                       if item["resolution"] == resolution and item["case"] == case_index)
                  for resolution in resolutions]
        axes[1].loglog(resolutions, errors, "o-", alpha=0.65, linewidth=1)
    first = summary["by_resolution"]["16"]["rmse_median_K"]
    axes[1].loglog(resolutions, first * (16 / np.array(resolutions, dtype=float)) ** 2,
                   "k--", linewidth=2, label="Second-order reference")
    axes[1].set(xlabel="Cells per dimension", ylabel="RMSE vs analytic solution (K)", title="Spatial error converges; time error checked")
    axes[1].legend(fontsize=8)
    axes[1].set_xticks(resolutions, labels=[str(value) for value in resolutions])
    axes[1].xaxis.set_minor_formatter(NullFormatter())
    for axis in axes:
        axis.grid(True, alpha=0.2)
    figure.suptitle("Synthetic insulated heat diffusion - numerical feasibility, NOT a furnace", fontsize=12)
    figure.savefig(ROOT / "results/cost-error.png", dpi=150)
    plt.close(figure)
    print("PASS wrote results/cost-error.png")


if __name__ == "__main__":
    main()
