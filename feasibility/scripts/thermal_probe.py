import argparse
import json
import os
import platform
import time
from pathlib import Path


for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["MPLBACKEND"] = "Agg"

import numpy as np
import scipy
from pde import CartesianGrid, DiffusionPDE, ScalarField, ScipySolver
from scipy.stats import spearmanr


ROOT = Path(__file__).resolve().parents[1]
MODES = [(1, 1), (3, 2), (5, 4)]
DIFFUSIVITY = 0.01
FINAL_TIME = 1.0
BASE_TEMPERATURE = 300.0
RTOL = 1e-10
ATOL = 1e-11


def profile(grid, amplitudes, elapsed, discrete=False):
    coordinates = grid.cell_coords
    resolution = grid.shape[0]
    values = np.zeros(grid.shape)
    for amplitude, (mode_x, mode_y) in zip(amplitudes, MODES, strict=True):
        if discrete:
            decay = 4 * DIFFUSIVITY * resolution**2 * (
                np.sin(np.pi * mode_x / (2 * resolution)) ** 2
                + np.sin(np.pi * mode_y / (2 * resolution)) ** 2
            )
        else:
            decay = DIFFUSIVITY * np.pi**2 * (mode_x**2 + mode_y**2)
        values += amplitude * np.exp(-decay * elapsed) * (
            np.cos(np.pi * mode_x * coordinates[..., 0])
            * np.cos(np.pi * mode_y * coordinates[..., 1])
        )
    return values


def simulate(resolution, amplitudes, tolerance_scale=1.0):
    wall_start, cpu_start = time.perf_counter(), time.process_time()
    grid = CartesianGrid([[0, 1], [0, 1]], [resolution, resolution], periodic=False)
    initial = ScalarField(grid, profile(grid, amplitudes, 0))
    equation = DiffusionPDE(diffusivity=DIFFUSIVITY, bc={"derivative": 0})
    result, info = equation.solve(
        initial, t_range=FINAL_TIME, solver=ScipySolver, tracker=None, ret_info=True,
        backend="numpy", method="RK45",
        rtol=RTOL * tolerance_scale, atol=ATOL * tolerance_scale,
    )
    cpu_seconds, wall_seconds = time.process_time() - cpu_start, time.perf_counter() - wall_start
    exact = profile(grid, amplitudes, FINAL_TIME)
    semidiscrete = profile(grid, amplitudes, FINAL_TIME, discrete=True)
    temporal_error = float(np.max(np.abs(result.data - semidiscrete)))
    spatial_error = float(np.max(np.abs(semidiscrete - exact)))
    record = {
        "resolution": resolution, "amplitudes": list(amplitudes),
        "wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds,
        "max_absolute_error_K": float(np.max(np.abs(result.data - exact))),
        "rmse_K": float(np.sqrt(np.mean((result.data - exact) ** 2))),
        "spatial_max_error_K": spatial_error, "temporal_max_error_K": temporal_error,
        "mean_drift_K": float(abs(result.average - initial.average)),
        "final_nonuniformity_std_K": float(np.std(result.data)),
        "semidiscrete_nonuniformity_std_K": float(np.std(semidiscrete)),
        "rhs_evaluations": int(info["solver"]["steps"]),
        "tolerance_scale": tolerance_scale,
    }
    assert np.isfinite(result.data).all()
    assert record["mean_drift_K"] < 1e-8, record
    assert temporal_error < 1e-6, record
    assert temporal_error < spatial_error * 0.01, record
    assert abs(record["final_nonuniformity_std_K"] - record["semidiscrete_nonuniformity_std_K"]) < 1e-6
    assert float(result.data.min()) >= float(initial.data.min()) - 1e-6
    assert float(result.data.max()) <= float(initial.data.max()) + 1e-6
    return record


def append_record(path, record):
    with path.open("a") as output:
        output.write(json.dumps(record) + "\n")
        output.flush()
        os.fsync(output.fileno())


def summarize(records, resolutions, case_count):
    summaries = {}
    for resolution in resolutions:
        samples = [record for record in records if record["resolution"] == resolution]
        walls = [record["wall_seconds"] for record in samples]
        summaries[resolution] = {
            "samples": len(samples), "wall_median_seconds": float(np.median(walls)),
            "wall_q25_seconds": float(np.quantile(walls, 0.25)),
            "wall_q75_seconds": float(np.quantile(walls, 0.75)),
            "cpu_median_seconds": float(np.median([record["cpu_seconds"] for record in samples])),
            "rmse_median_K": float(np.median([record["rmse_K"] for record in samples])),
            "max_error_K": max(record["max_absolute_error_K"] for record in samples),
            "max_temporal_error_K": max(record["temporal_max_error_K"] for record in samples),
        }
    orders = []
    for case_index in range(case_count):
        selected = {resolution: next(
            record for record in records
            if record["case"] == case_index and record["resolution"] == resolution
        ) for resolution in resolutions}
        for coarse, fine in zip(resolutions[:-1], resolutions[1:]):
            order = float(np.log(selected[coarse]["rmse_K"] / selected[fine]["rmse_K"]) / np.log(fine / coarse))
            assert 1.5 < order < 2.5, (case_index, coarse, fine, order)
            orders.append({"case": case_index, "coarse": coarse, "fine": fine, "order": order})
    paired = []
    fine_resolution, coarse_resolution = resolutions[-1], resolutions[0]
    for fine_record in records:
        if fine_record["resolution"] != fine_resolution:
            continue
        coarse_record = next(record for record in records if (
            record["case"] == fine_record["case"] and record["repeat"] == fine_record["repeat"]
            and record["resolution"] == coarse_resolution
        ))
        paired.append(fine_record["wall_seconds"] / coarse_record["wall_seconds"])
    coarse_outputs, fine_outputs = [], []
    for case_index in range(case_count):
        for resolution, outputs in [(coarse_resolution, coarse_outputs), (fine_resolution, fine_outputs)]:
            outputs.append(next(record["final_nonuniformity_std_K"] for record in records
                                if record["case"] == case_index and record["resolution"] == resolution))
    return {
        "status": "PASS", "by_resolution": summaries, "spatial_convergence_orders": orders,
        "paired_fine_to_coarse_wall_ratio_median": float(np.median(paired)),
        "paired_fine_to_coarse_wall_ratio_range": [float(min(paired)), float(max(paired))],
        "nonuniformity_spearman": (
            float(spearmanr(coarse_outputs, fine_outputs).statistic) if case_count > 1 else None
        ),
        "ranking_sample_count": case_count,
        "limitations": [
            "Synthetic source-free insulated heat relaxation, not a furnace, radiation model or heating optimization task.",
            "Temperature deviation is solved; add 300 K for absolute temperature. Material parameters are synthetic.",
            "Only grid resolution changes; adaptive RK45 uses common tolerances but takes different steps per grid.",
            "Times include grid, initial condition, operator/solver setup and solve; exclude imports and error evaluation.",
            "Analytic continuum and semidiscrete solutions validate errors; the finest grid is not physical truth.",
            "No artificial sleep, no GPU, no inference/optimization speedup claim; shared-machine timing is exploratory.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    label = "pilot" if args.pilot else "thermal"
    results = ROOT / "results"
    config_path, raw_path = results / f"{label}-config.json", results / f"{label}-raw.jsonl"
    resolutions = [16, 32, 64, 128]
    case_count, repeats = (1, 1) if args.pilot else (8, 5)
    generator = np.random.default_rng(20260924)
    amplitudes = generator.uniform([2, 0.5, 0.1], [10, 5, 2], size=(case_count, 3)).tolist()
    config = {
        "resolutions": resolutions, "cases": amplitudes, "repeats": repeats,
        "diffusivity_m2_per_s": DIFFUSIVITY, "final_time_s": FINAL_TIME,
        "domain_m": [[0, 1], [0, 1]], "modes": MODES,
        "base_temperature_K": BASE_TEMPERATURE, "rtol": RTOL, "atol": ATOL,
        "seed": 20260924, "backend": "numpy", "solver": "scipy RK45",
        "platform": platform.platform(), "numpy": np.__version__, "scipy": scipy.__version__,
    }
    serialized = json.dumps(config, indent=2) + "\n"
    if config_path.exists():
        assert config_path.read_text() == serialized, "Configuration changed; use a new result directory"
    else:
        config_path.write_text(serialized)
    records = [json.loads(line) for line in raw_path.read_text().splitlines()] if raw_path.exists() else []
    existing = {(record["repeat"], record["case"], record["resolution"]) for record in records}
    warmups = []
    for resolution in resolutions:
        sample = simulate(resolution, amplitudes[0])
        warmups.append(sample)
        print(f"WARMUP n={resolution} wall={sample['wall_seconds']:.4f}s error={sample['rmse_K']:.6g}K", flush=True)
    (results / f"{label}-warmups.json").write_text(json.dumps(warmups, indent=2) + "\n")
    jobs = [(repeat, case_index, resolution) for repeat in range(repeats)
            for case_index in range(case_count) for resolution in resolutions]
    generator.shuffle(jobs)
    for repeat, case_index, resolution in jobs:
        if (repeat, case_index, resolution) in existing:
            continue
        record = simulate(resolution, amplitudes[case_index])
        record.update(repeat=repeat, case=case_index)
        append_record(raw_path, record)
        records.append(record)
        print(f"MEASURE {len(records)}/{len(jobs)} case={case_index} n={resolution} wall={record['wall_seconds']:.4f}s", flush=True)
    summary = summarize(records, resolutions, case_count)
    if not args.pilot:
        checks = []
        for resolution in [128, 256]:
            check = simulate(resolution, amplitudes[0], tolerance_scale=0.01)
            checks.append(check)
        summary["tight_tolerance_checks"] = checks
        original = next(record for record in records if record["resolution"] == 128 and record["case"] == 0)
        assert abs(checks[0]["rmse_K"] - original["rmse_K"]) < 1e-6
        extra_order = float(np.log(checks[0]["rmse_K"] / checks[1]["rmse_K"]) / np.log(2))
        assert 1.5 < extra_order < 2.5
        summary["extra_refinement_order_128_to_256"] = extra_order
    (results / f"{label}-summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
