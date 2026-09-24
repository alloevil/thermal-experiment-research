"""Paired, one-next-experiment comparison; keeps rejected and unresolved results."""

import json
import time
from pathlib import Path

from core import ExperimentBank, NAMES, example_case, simulate, np
from cli import save, new_directory


ROOT = Path(__file__).resolve().parent


def main():
    output = ROOT / "evaluation"
    new_directory(output)
    started = time.perf_counter()
    case = example_case()
    generator = np.random.default_rng(20261002)
    truths = []
    for index in range(16):
        label = NAMES[index % 2]
        truths.append({"label": label, "convection": float(generator.uniform(1.18, 1.55)) if label == "convection" else 1.,
                       "offset": float(generator.uniform(-.85, -.25)) if label == "offset" else 0.,
                       "gain": float(generator.uniform(.97, 1.03)), "capacity": float(generator.uniform(.97, 1.03))})
    save(output / "protocol.json", {"case": case, "truths": truths, "seed": 20261002,
                                    "policies": ["information_gain", "fixed_cooldown", "random", "mean_separation"],
                                    "budget": "exactly one enabled cost=1 experiment; even when initial posterior already strong",
                                    "information_gain_samples": 128})
    bank = ExperimentBank(case)
    enabled = [name for name, spec in case["experiments"].items() if spec["enabled"] and spec["cost"] <= case["budget"]]
    trials = []
    planning_time = 0.
    for index, truth in enumerate(truths):
        parameters = {key: value for key, value in truth.items() if key != "label"}
        observations = {}
        for name in ["initial", *enabled]:
            experiment = case["experiments"][name]
            measured = simulate(experiment, **parameters, cells=96) + generator.normal(0, experiment["sigma_K"], len(experiment["observations"]))
            observations[name] = {"id": f"trial-{index}-{name}", "experiment": name, "values_K": measured.tolist()}
        initial_data = {"records": [observations["initial"]]}
        initial, weights = bank.posterior(initial_data)
        begin = time.perf_counter()
        ranked = bank.score_experiments(weights)
        planning_time += time.perf_counter() - begin
        selected = {"information_gain": ranked[0]["experiment"], "fixed_cooldown": "cooldown",
                    "random": enabled[int(generator.integers(len(enabled)))],
                    "mean_separation": max(ranked, key=lambda item: (item["mean_separation_score"], item["experiment"]))["experiment"]}
        outcomes = {}
        for policy, name in selected.items():
            posterior, _ = bank.posterior({"records": [observations["initial"], observations[name]]})
            probability = posterior["model_probability"]["convection"]
            outcomes[policy] = {"experiment": name, "posterior": posterior,
                                "brier": (probability - (truth["label"] == "convection"))**2,
                                "decided": posterior["status"] == "supported_hypothesis",
                                "wrong": posterior["status"] == "supported_hypothesis" and posterior["supported"] != truth["label"]}
        trial = {"id": index, "truth": truth, "observations": observations, "initial": initial,
                 "ranked_experiments": ranked, "outcomes": outcomes}
        trials.append(trial)
        save(output / f"trial-{index:02}.json", trial)
        print(f"TRIAL {index} truth={truth['label']} choices={selected} status=" + str({policy: outcome['posterior']['status'] for policy, outcome in outcomes.items()}), flush=True)
    policies = {}
    for policy in selected:
        outcomes = [trial["outcomes"][policy] for trial in trials]
        policies[policy] = {"trials": len(outcomes), "decided": sum(item["decided"] for item in outcomes),
                            "wrong_decisions": sum(item["wrong"] for item in outcomes),
                            "ambiguous": sum(item["posterior"]["status"] == "ambiguous" for item in outcomes),
                            "unsupported": sum(item["posterior"]["status"] == "unsupported" for item in outcomes),
                            "mean_brier_all_cases": float(np.mean([item["brier"] for item in outcomes])),
                            "selection_counts": {name: sum(item["experiment"] == name for item in outcomes) for name in enabled}}
    summary = {"status": "COMPLETED", "policies": policies, "planning_wall_seconds": planning_time,
               "cached_planner_ODE_calls": bank.solve_calls, "total_wall_seconds": time.perf_counter() - started,
               "limits": ["16 synthetic objects, finite approximate priors, same family of equations; no population significance claim.",
                          "An observation for every plan was simulated offline to permit paired policy evaluation; real use would only execute the selected plan.",
                          "Brier counts all cases, including unsupported; abstention is reported separately. Mean-separation is a heuristic, not D-optimal or SOTA.",
                          "No independent reference is available in this comparison; each selected thermal plan costs one declared budget unit, not equal duration or energy."]}
    save(output / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
