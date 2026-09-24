import ast
import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ["MPLBACKEND"] = "Agg"
os.environ["SMOKE_TEST"] = "1"

import numpy as np


def save(name, data):
    (ROOT / "results" / name).write_text(json.dumps(data, indent=2) + "\n")


def verify_sources():
    for record in json.loads((ROOT / "upstream/manifest.json").read_text()):
        actual = hashlib.sha256((ROOT / record["file"]).read_bytes()).hexdigest()
        assert actual == record["sha256"], record["file"]


def run_heat():
    import matplotlib.pyplot as plt
    from pde import CartesianGrid, DiffusionPDE, ScalarField, UnitGrid

    namespace = {"__name__": "__main__"}
    start = time.perf_counter()
    source = ROOT / "upstream/pde-example.py"
    exec(compile(source.read_text(), str(source), "exec"), namespace)
    elapsed = time.perf_counter() - start
    initial, final = namespace["state"], namespace["result"]
    assert np.isfinite(final.data).all()
    assert abs(final.average - initial.average) < 1e-8
    assert final.fluctuations < initial.fluctuations
    plt.savefig(ROOT / "results/upstream-heat.png", dpi=140)
    plt.close("all")
    print(f"PASS original heat example: {elapsed:.3f}s", flush=True)
    tests_source = (ROOT / "upstream/pde-tests.py").read_text()
    tree = ast.parse(tests_source)
    names = [
        "test_simple_diffusion_value",
        "test_simple_diffusion_flux_right",
        "test_simple_diffusion_flux_left",
    ]
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(selected) == len(names)
    scope = {
        "np": np, "CartesianGrid": CartesianGrid, "DiffusionPDE": DiffusionPDE,
        "ScalarField": ScalarField, "UnitGrid": UnitGrid,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "upstream/pde-tests.py", "exec"), scope)
    tests = []
    for name in names:
        start = time.perf_counter()
        scope[name](np.random.default_rng(20260924))
        duration = time.perf_counter() - start
        tests.append({"name": name, "status": "PASS", "wall_seconds": duration})
        print(f"PASS original {name}: {duration:.3f}s", flush=True)
    save("upstream-heat.json", {
        "status": "PASS", "example_wall_seconds": elapsed,
        "initial_mean": float(initial.average), "final_mean": float(final.average),
        "initial_std": float(initial.fluctuations), "final_std": float(final.fluctuations),
        "tests": tests,
        "execution_notes": [
            "Original example executed unchanged with headless plotting; its default RNG is not overridden.",
            "Three original test function ASTs run unchanged with a seeded RNG fixture substitute.",
            "This is not execution of the entire upstream pytest suite.",
        ],
    })


def run_botorch():
    import torch

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(20260924)
    np.random.seed(20260924)
    torch.use_deterministic_algorithms(True)
    notebook = json.loads((ROOT / "upstream/botorch-tutorial.ipynb").read_text())
    namespace = {"__name__": "__main__"}
    cells, recommendations, transforms = [], [], []
    start_total = time.perf_counter()
    for index, cell in enumerate(notebook["cells"]):
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        lines = []
        for line in source.splitlines():
            if line.strip().startswith("%pip "):
                transforms.append({"cell": index, "original": line, "replacement": "pass"})
                lines.append(line[:len(line) - len(line.lstrip())] + "pass")
            else:
                lines.append(line)
        source = "\n".join(lines)
        print(f"BEGIN cell {index}", flush=True)
        start = time.perf_counter()
        exec(compile(source, f"botorch-tutorial.ipynb:cell{index}", "exec"), namespace)
        elapsed = time.perf_counter() - start
        cells.append({"cell": index, "wall_seconds": elapsed, "status": "PASS"})
        if "final_rec = get_recommendation(model)" in source:
            candidate = namespace["final_rec"].detach()
            objective = namespace["problem"](candidate).detach()
            assert bool(torch.isfinite(candidate).all() and torch.isfinite(objective).all())
            assert bool(((candidate >= 0) & (candidate <= 1)).all())
            assert bool(torch.all(candidate[..., -1] == 1))
            recommendations.append({
                "cell": index, "candidate": candidate.tolist(), "objective": objective.tolist(),
                "tutorial_cost": float(namespace["cumulative_cost"]),
                "observations": len(namespace["train_x"]),
            })
        save("upstream-botorch-progress.json", {"cells": cells, "recommendations": recommendations})
        print(f"PASS cell {index}: {elapsed:.3f}s", flush=True)
    assert namespace["N_ITER"] == 2
    assert len(recommendations) == 2
    save("upstream-botorch.json", {
        "status": "PASS", "mode": "upstream SMOKE_TEST=1", "seed": 20260924,
        "threads": 1, "wall_seconds": time.perf_counter() - start_total,
        "cells": cells, "recommendations": recommendations, "transforms": transforms,
        "execution_notes": [
            "Only the unreachable Colab pip magic is replaced by pass; all problem and optimization code is unchanged.",
            "Upstream EI comparison uses separate initial draws and unequal costs, so it is NOT a controlled performance comparison.",
            "Tutorial cost is a synthetic fidelity cost and excludes initialization, optimizer time and final evaluation.",
            "The original final model is not refit after the last observation batch; retained to reproduce upstream behavior.",
        ],
    })


if __name__ == "__main__":
    verify_sources()
    print(f"Python {sys.version}; platform {platform.platform()}", flush=True)
    {"heat": run_heat, "botorch": run_botorch}[sys.argv[1]]()
