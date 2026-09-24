"""Local recommend/update loop for a bounded thermal model-discrimination task."""

import argparse
import copy
import json
import sys
import time
from pathlib import Path

from core import ExperimentBank, add_measurement, card, example_case, np, require, simulate


def load(path):
    def invalid(value):
        raise ValueError(f"Invalid JSON number: {value}")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(), parse_constant=invalid, object_pairs_hook=pairs)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def new_directory(path):
    require(not path.exists() and not path.is_symlink(), "Output already exists; choose a new directory")
    root = Path(__file__).resolve().parents[1]
    reserved = ["radiation", "calibration", "feasibility", "sensitivity", "model_mismatch", "bias_boundary", "reference_correction", "evidence_report"]
    require(not any(path.resolve().is_relative_to(root / name) for name in reserved), "Do not write into archived studies")
    path.mkdir(parents=True, exist_ok=False)


def write_recommendation(directory, result):
    save(directory / "recommendation.json", result)
    (directory / "recommendation.md").write_text(card(result))


def demo(directory):
    new_directory(directory)
    case = example_case()
    hidden = {"convection": 1.4, "gain": 1., "capacity": 1., "offset": 0.}
    generator = np.random.default_rng(20261001)
    initial = case["experiments"]["initial"]
    observed = simulate(initial, **hidden, cells=96) + generator.normal(0, initial["sigma_K"], 1)
    observations = {"records": [{"id": "initial-1", "experiment": "initial", "values_K": observed.tolist()}]}
    save(directory / "case.json", case)
    save(directory / "observations.json", observations)
    save(directory / "simulation-truth.json", {"purpose": "Demo evaluation only; never supplied to recommend or update", "parameters": hidden})
    bank = ExperimentBank(case)
    started = time.perf_counter()
    result = bank.recommend(observations)
    write_recommendation(directory, result)
    if result["recommendation"]:
        selected = result["recommendation"]
        experiment = case["experiments"][selected]
        values = simulate(experiment, **hidden, cells=96) + generator.normal(0, experiment["sigma_K"], len(experiment["observations"]))
        measurement = {"id": "next-1", "experiment": selected, "values_K": values.tolist()}
        save(directory / "measurement.json", measurement)
        updated = add_measurement(case, observations, measurement)
        save(directory / "updated-observations.json", updated)
        after, _ = bank.posterior(updated)
        save(directory / "updated-posterior.json", after)
    else:
        after = None
    equivalent = copy.deepcopy(case)
    equivalent["grid"]["convection"] = [1.]
    equivalent["grid"]["offset_K"] = [0.]
    identical_result = ExperimentBank(equivalent).recommend(observations)
    save(directory / "indistinguishable.json", identical_result)
    outside = {"records": [{"id": "out-of-scope", "experiment": "initial", "values_K": [400.]}]}
    unsupported = bank.recommend(outside)
    save(directory / "unsupported.json", unsupported)
    require(identical_result["status"] == "not_distinguishable", "Equal candidates should not force a recommendation")
    require(unsupported["status"] == "unsupported", "Both bad candidates should be rejected")
    receipt = {"initial": result["posterior"], "selected": result["recommendation"], "updated": after,
               "indistinguishable": identical_result["status"], "outside_candidate_set": unsupported["status"],
               "planner_solver_calls": bank.solve_calls, "wall_seconds": time.perf_counter() - started,
               "scope": "One developer demonstration, not an algorithm benchmark or real device test"}
    save(directory / "demo-result.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demonstration = commands.add_parser("demo", help="Run synthetic end-to-end example plus abstention and rejection cases")
    demonstration.add_argument("--output", required=True, type=Path)
    for name in ["recommend", "update"]:
        sub = commands.add_parser(name)
        sub.add_argument("--case", required=True, type=Path)
        sub.add_argument("--observations", required=True, type=Path)
        sub.add_argument("--output", required=True, type=Path)
        if name == "update":
            sub.add_argument("--measurement", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            demo(args.output)
            return 0
        case, observations = load(args.case), load(args.observations)
        bank = ExperimentBank(case)
        if args.command == "update":
            updated = add_measurement(case, observations, load(args.measurement))
            posterior, _ = bank.posterior(updated)
            new_directory(args.output)
            save(args.output / "observations.json", updated)
            save(args.output / "posterior.json", posterior)
            print(json.dumps(posterior, ensure_ascii=False, indent=2))
        else:
            result = bank.recommend(observations)
            new_directory(args.output)
            write_recommendation(args.output, result)
            print(card(result))
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as error:
        print(f"Request rejected: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
