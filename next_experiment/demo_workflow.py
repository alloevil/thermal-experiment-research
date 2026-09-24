"""Run the research workflow across processes; synthetic observation requires opt-in."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import scipy

from cli import load, new_directory, save
from core import example_case, np, require, simulate


def run_cli(directory, command, *arguments):
    workflow = Path(__file__).resolve().with_name("workflow.py")
    invocation = [sys.executable, "-B", str(workflow), command, *map(str, arguments)]
    process = subprocess.run(invocation, cwd=directory,
                             env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TZ="UTC"),
                             capture_output=True, text=True, timeout=120)
    with (directory / "commands.log").open("a") as handle:
        handle.write(f"$ {shlex.join(invocation)}\n{process.stdout}{process.stderr}\nexit_code={process.returncode}\n\n")
    require(process.returncode == 0, f"{command} failed; see {directory / 'commands.log'}")


def demo(directory, approve_simulation):
    new_directory(directory)
    directory = directory.resolve()
    started = time.perf_counter()
    case = example_case()
    hidden = {"convection": 1.4, "offset": 0., "gain": 1., "capacity": 1.}
    generator = np.random.default_rng(20261001)
    initial = case["experiments"]["initial"]
    values = simulate(initial, **hidden, cells=96) + generator.normal(0, initial["sigma_K"], 1)
    observations = {"records": [{"id": "initial-1", "experiment": "initial", "values_K": values.tolist()}]}
    save(directory / "case.json", case)
    save(directory / "observations.json", observations)
    save(directory / "simulation-truth.json", {
        "parameters": hidden, "seed": 20261001, "cells": 96,
        "scope": "Existing developer fixture, not an unseen benchmark; never passed to workflow commands",
    })
    run_cli(directory, "plan", "--case", directory / "case.json", "--observations", directory / "observations.json",
            "--output", directory / "plan")
    session = load(directory / "plan/session.json")
    selected = session["proposal"]["recommendation"]["recommendation"]
    if approve_simulation and selected is not None:
        run_cli(directory, "review", "--session", directory / "plan/session.json",
                "--proposal-id", session["proposal_id"], "--experiment", selected,
                "--decision", "approve", "--reviewer", "simulation-demo-opt-in",
                "--acknowledge-research-only", "--output", directory / "review")
        experiment = case["experiments"][selected]
        values = simulate(experiment, **hidden, cells=96)
        values += generator.normal(0, experiment["sigma_K"], len(values))
        measurement = {"id": "next-1", "experiment": selected, "values_K": values.tolist()}
        save(directory / "measurement.json", measurement)
        run_cli(directory, "observe", "--session", directory / "review/session.json",
                "--measurement", directory / "measurement.json", "--origin", "simulated",
                "--output", directory / "completed")
        session = load(directory / "completed/session.json")
    result = {
        "stage": session["stage"], "selected": selected,
        "simulation_opt_in": approve_simulation,
        "initial": session["proposal"]["recommendation"]["posterior"], "outcome": session["outcome"],
        "wall_seconds": time.perf_counter() - started,
        "environment": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__},
        "scope": "Synthetic developer demonstration; no real engineer authentication, no hardware or AI performance claim",
        "engineering_release": "not_supported",
    }
    save(directory / "result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--approve-simulation", action="store_true",
                        help="Explicitly opt in to the synthetic next observation; not actual engineer/device approval")
    args = parser.parse_args(argv)
    try:
        demo(args.output, args.approve_simulation)
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Demo stopped; existing stage files retained: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
