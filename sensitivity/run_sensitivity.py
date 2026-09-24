import hashlib
import itertools
import json
import os
import platform
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RADIATION = ROOT.parent / "radiation"
sys.path.insert(0, str(RADIATION))

from model import HeatingModel, Parameters, metrics, np
from scipy.stats import qmc


FACTORS = ["emissivity", "convection", "heat_capacity", "power_gain", "axial_conductance"]
LIMITS = ["peak", "spread", "final_low", "final_high"]
KNOTS = np.array([0, 60, 120, 180], dtype=float)


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_json(path, record):
    with path.open("a") as output:
        output.write(json.dumps(record, allow_nan=False) + "\n")
        output.flush()
        os.fsync(output.fileno())


def temperature_margins(summary):
    return dict(zip(LIMITS, [360 - summary["peak_K"], 12 - summary["max_spread_K"],
                             summary["final_mean_K"] - 348, 352 - summary["final_mean_K"]], strict=True))


def power_check(powers):
    slew = np.diff(powers, axis=0) / np.diff(KNOTS)[:, None]
    return bool(np.min(powers) >= -1e-9 and np.max(powers) <= 1 + 1e-9 and np.max(abs(slew)) <= 0.015 + 1e-9)


def cases():
    output = [{"id": "nominal", "group": "nominal", "factors": dict.fromkeys(FACTORS, 1.0)}]
    for name in FACTORS:
        for factor in [0.9, 0.95, 1.05, 1.1]:
            values = dict.fromkeys(FACTORS, 1.0)
            values[name] = factor
            output.append({"id": f"oat-{name}-{factor}", "group": "oat", "factor": name, "factors": values})
    for index, values in enumerate(itertools.product([0.9, 1.1], repeat=5)):
        output.append({"id": f"corner-{index:03d}", "group": "corners", "factors": dict(zip(FACTORS, values, strict=True))})
    samples = 0.9 + 0.2 * qmc.Sobol(d=5, scramble=True, seed=20260924).random_base2(m=7)
    for index, values in enumerate(samples):
        output.append({"id": f"sobol-{index:03d}", "group": "sobol", "factors": dict(zip(FACTORS, values.tolist(), strict=True))})
    assert len(output) == 181 and len({item["id"] for item in output}) == 181
    return output


def evaluate(case, command_powers, refined=False):
    values = case["factors"]
    nominal = Parameters()
    parameters = replace(nominal, **{
        name: getattr(nominal, name) * values[name] for name in FACTORS if name != "power_gain"
    })
    assert 0 < parameters.emissivity <= 1
    powers = command_powers * values["power_gain"]
    model = HeatingModel(cells=192 if refined else 96, parameters=parameters)
    result = model.solve(powers, sample_step=0.0625 if refined else 0.25,
                         rtol=1e-11 if refined else 1e-10, atol=1e-12 if refined else 1e-11)
    summary = metrics(model, result)
    assert summary["max_balance_residual_J"] < 1e-4
    exact_absorbed = float(np.trapezoid(powers.sum(axis=1), KNOTS))
    assert abs(exact_absorbed - summary["absorbed_J"]) < 1e-4
    convection, radiation = model.losses(result["temperature"])
    loss_integrals = np.array([np.trapezoid(convection.sum(axis=1), result["time"]),
                               np.trapezoid(radiation.sum(axis=1), result["time"])])
    integration_errors = loss_integrals - result["ledger"][-1, 1:]
    assert np.max(abs(integration_errors)) < 0.1
    margins = temperature_margins(summary)
    violated = [name for name, margin in margins.items() if margin < -1e-5]
    command_valid, actual_valid = power_check(command_powers), power_check(powers)
    trace_path = ROOT / "results/traces" / f"{'refined-' if refined else ''}{case['id']}.npz"
    np.savez_compressed(
        trace_path, time=result["time"], mean=result["temperature"].mean(axis=1),
        std=result["temperature"].std(axis=1), minimum=result["temperature"].min(axis=1),
        maximum=result["temperature"].max(axis=1), ledger=result["ledger"],
        convection=convection.sum(axis=1), radiation=radiation.sum(axis=1),
    )
    return {
        "id": case["id"], "group": case["group"], "factors": values,
        "parameters": asdict(parameters), "actual_powers_W": powers.tolist(),
        "cells": model.cells, "sample_step_s": 0.0625 if refined else 0.25,
        "metrics": summary, "margins_K": margins, "violated": violated,
        "command_valid": command_valid, "actual_power_valid": actual_valid,
        "feasible_at_samples": not violated and command_valid and actual_valid,
        "near_boundary": min(abs(value) for value in margins.values()) <= 0.05,
        "independent_loss_integral_errors_J": integration_errors.tolist(),
        "trace": str(trace_path.relative_to(ROOT)), "trace_sha256": digest(trace_path),
    }


def select_refinements(records):
    selected = {"nominal"}
    for quantity, selection in [("peak_K", max), ("max_spread_K", max), ("final_mean_K", min),
                                ("final_mean_K", max), ("mse_K2", max)]:
        selected.add(selection(records, key=lambda record: record["metrics"][quantity])["id"])
    nearest = sorted(records, key=lambda record: (min(abs(value) for value in record["margins_K"].values()), record["id"]))[:4]
    selected.update(record["id"] for record in nearest)
    return sorted(selected)


def main():
    started = time.perf_counter()
    results = ROOT / "results"
    (results / "traces").mkdir(parents=True, exist_ok=True)
    dependencies = {
        "protocol.md": ROOT / "protocol.md", "run_sensitivity.py": Path(__file__),
        "radiation/model.py": RADIATION / "model.py",
        "radiation/results/experiment.json": RADIATION / "results/experiment.json",
        "feasibility/requirements.lock": ROOT.parent / "feasibility/requirements.lock",
    }
    experiment = json.loads(dependencies["radiation/results/experiment.json"].read_text())
    command_powers = np.array(experiment["optimized_powers_W"])
    config = {"cases": cases(), "command_powers_W": command_powers.tolist(),
              "hashes": {name: digest(path) for name, path in dependencies.items()},
              "platform": platform.platform(), "python": sys.version, "numpy": np.__version__}
    config_path = results / "config.json"
    if config_path.exists():
        assert json.loads(config_path.read_text()) == config, "Configuration or dependency changed; archive this run first"
    else:
        save_json(config_path, config)
    records_path, refinements_path = results / "scan.jsonl", results / "refinements.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()] if records_path.exists() else []
    refined_records = [json.loads(line) for line in refinements_path.read_text().splitlines()] if refinements_path.exists() else []
    before = len(records)
    for record in records + refined_records:
        assert digest(ROOT / record["trace"]) == record["trace_sha256"]
    assert len({record["id"] for record in records}) == len(records)
    completed = {record["id"] for record in records}
    for case in config["cases"]:
        if case["id"] in completed:
            continue
        try:
            record = evaluate(case, command_powers)
            if case["id"] == "nominal":
                for quantity in ["mse_K2", "peak_K", "max_spread_K", "final_mean_K", "final_std_K"]:
                    assert abs(record["metrics"][quantity] - experiment["optimized"][quantity]) < 1e-6
            append_json(records_path, record)
            records.append(record)
            print(f"SCAN {len(records)}/181 {case['id']} final={record['metrics']['final_mean_K']:.4f}K violated={record['violated']}", flush=True)
        except Exception as error:
            append_json(results / "failures.jsonl", {"id": case["id"], "error": repr(error)})
            raise
    selected = select_refinements(records)
    save_json(results / "refinement-selection.json", selected)
    for case_id in selected:
        if any(record["id"] == case_id for record in refined_records):
            continue
        case = next(item for item in config["cases"] if item["id"] == case_id)
        refined = evaluate(case, command_powers, refined=True)
        original = next(item for item in records if item["id"] == case_id)
        refined["metric_changes"] = {quantity: refined["metrics"][quantity] - original["metrics"][quantity]
                                     for quantity in ["mse_K2", "peak_K", "max_spread_K", "final_mean_K"]}
        refined["classification_changed"] = refined["violated"] != original["violated"]
        append_json(refinements_path, refined)
        refined_records.append(refined)
        print(f"REFINED {case_id} changes={refined['metric_changes']} flipped={refined['classification_changed']}", flush=True)
    groups = {}
    for group in ["nominal", "oat", "corners", "sobol"]:
        subset = [record for record in records if record["group"] == group]
        groups[group] = {
            "count": len(subset), "feasible": sum(record["feasible_at_samples"] for record in subset),
            "violations": {limit: sum(limit in record["violated"] for record in subset) for limit in LIMITS},
            "near_boundary": [record["id"] for record in subset if record["near_boundary"]],
            "final_mean_range_K": [min(record["metrics"]["final_mean_K"] for record in subset), max(record["metrics"]["final_mean_K"] for record in subset)],
        }
    sensitivities = {}
    for factor in FACTORS:
        low = next(record for record in records if record["id"] == f"oat-{factor}-0.95")
        high = next(record for record in records if record["id"] == f"oat-{factor}-1.05")
        sensitivities[factor] = (high["metrics"]["final_mean_K"] - low["metrics"]["final_mean_K"]) / 10
    refined_ok = all(abs(record["metric_changes"][quantity]) < 0.01
                     for record in refined_records for quantity in ["peak_K", "max_spread_K", "final_mean_K"])
    summary = {
        "status": "PASS" if refined_ok else "REFINEMENT_FAILED", "groups": groups,
        "local_final_mean_K_per_percentage_point": sensitivities,
        "worst_peak": max(records, key=lambda record: record["metrics"]["peak_K"])["id"],
        "worst_spread": max(records, key=lambda record: record["metrics"]["max_spread_K"])["id"],
        "lowest_final": min(records, key=lambda record: record["metrics"]["final_mean_K"])["id"],
        "highest_final": max(records, key=lambda record: record["metrics"]["final_mean_K"])["id"],
        "refined_cases": selected,
        "refinement_flips": [record["id"] for record in refined_records if record["classification_changed"]],
        "summed_scan_solve_seconds": sum(record["metrics"]["wall_seconds"] for record in records),
        "limitations": ["Synthetic sensitivity box, not a calibrated uncertainty distribution or failure probability.",
                        "One fixed open-loop input; no recalibration, robustness optimization, or AI comparison.",
                        "Grid refinement uses the same physical model; not independent solver or hardware validation."],
    }
    save_json(results / "summary.json", summary)
    append_json(results / "invocations.jsonl", {"existing_scan_records": before, "new_scan_records": len(records) - before,
                                               "wall_seconds": time.perf_counter() - started})
    print(json.dumps(summary, indent=2), flush=True)
    assert refined_ok, "Refinement differences exceeded preregistered threshold"


if __name__ == "__main__":
    main()
