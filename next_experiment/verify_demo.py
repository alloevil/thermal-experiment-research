"""Check the real CLI round trip and recompute paired evaluation results."""

import json
import copy
import subprocess
import sys
import tempfile
from pathlib import Path

from core import ExperimentBank, add_measurement, np


ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text())


def main():
    demo = ROOT / "demo"
    case, observed = load(demo / "case.json"), load(demo / "observations.json")
    before = (demo / "observations.json").read_bytes()
    with tempfile.TemporaryDirectory(prefix="next-experiment-cli-") as temporary:
        temporary = Path(temporary)
        def invoke(arguments, expected=0):
            result = subprocess.run([sys.executable, "-B", str(ROOT / "cli.py"), *arguments], cwd=temporary,
                                    capture_output=True, text=True, timeout=120, check=False)
            if result.returncode != expected:
                raise RuntimeError(result.stderr)
            return result
        recommended = temporary / "recommended"
        invoke(["recommend", "--case", str(demo / "case.json"), "--observations", str(demo / "observations.json"), "--output", str(recommended)])
        result = load(recommended / "recommendation.json")
        assert result == load(demo / "recommendation.json")
        assert result["posterior"]["status"] == "ambiguous" and result["recommendation"]
        updated = temporary / "updated"
        invoke(["update", "--case", str(demo / "case.json"), "--observations", str(demo / "observations.json"),
                "--measurement", str(demo / "measurement.json"), "--output", str(updated)])
        assert load(updated / "posterior.json") == load(demo / "updated-posterior.json")
        assert load(updated / "observations.json") == load(demo / "updated-observations.json")
        duplicate = temporary / "duplicate"
        invoke(["update", "--case", str(demo / "case.json"), "--observations", str(updated / "observations.json"),
                "--measurement", str(demo / "measurement.json"), "--output", str(duplicate)], expected=2)
        assert not duplicate.exists()
        assert (demo / "observations.json").read_bytes() == before
    print("PASS separate recommend/update CLI round trip from unrelated cwd; duplicate observations rejected", flush=True)
    assert load(demo / "indistinguishable.json")["status"] == "not_distinguishable"
    assert load(demo / "unsupported.json")["status"] == "unsupported"
    print("PASS equal-candidate abstention and out-of-candidate rejection", flush=True)
    limited = copy.deepcopy(case)
    limited["max_predicted_temperature_K"] = 360
    limited_result = ExperimentBank(limited).recommend(observed)
    assert limited_result["recommendation"] == "cooldown"
    assert any(item["experiment"] == "heat_high" for item in limited_result["excluded_experiments"])
    (demo / "temperature-limited-recommendation.json").write_text(json.dumps(limited_result, indent=2) + "\n")
    print("PASS real 360K limit excludes heat_high and recommends permitted cooldown", flush=True)
    evaluation = ROOT / "evaluation"
    config = load(evaluation / "protocol.json")
    bank = ExperimentBank(config["case"])
    totals = {name: {"decided": 0, "wrong_decisions": 0, "ambiguous": 0, "unsupported": 0, "brier": []}
              for name in config["policies"]}
    for index in range(16):
        trial = load(evaluation / f"trial-{index:02}.json")
        initial = trial["observations"]["initial"]
        for policy, stored in trial["outcomes"].items():
            plan = stored["experiment"]
            assert config["case"]["experiments"][plan]["enabled"]
            assert config["case"]["experiments"][plan]["cost"] == 1
            data = {"records": [initial, trial["observations"][plan]]}
            posterior, _ = bank.posterior(data)
            assert posterior == stored["posterior"]
            assert 0 <= posterior["model_probability"]["convection"] <= 1
            tally = totals[policy]
            decided = posterior["status"] == "supported_hypothesis"
            tally["decided"] += decided
            tally["wrong_decisions"] += decided and posterior["supported"] != trial["truth"]["label"]
            tally["ambiguous"] += posterior["status"] == "ambiguous"
            tally["unsupported"] += posterior["status"] == "unsupported"
            brier = (posterior["model_probability"]["convection"] - (trial["truth"]["label"] == "convection"))**2
            assert np.isclose(brier, stored["brier"])
            tally["brier"].append(brier)
    summary = load(evaluation / "summary.json")
    for policy, tally in totals.items():
        for name in ["decided", "wrong_decisions", "ambiguous", "unsupported"]:
            assert summary["policies"][policy][name] == tally[name]
        assert np.isclose(summary["policies"][policy]["mean_brier_all_cases"], np.mean(tally["brier"]))
    assert all(bank.peak_temperatures[plan] <= config["case"]["max_predicted_temperature_K"] for plan in ["heat_low", "heat_high", "cooldown"])
    print("PASS all 64 policy/object updates recomputed with paired data and matching budget; temperature screen passes", flush=True)
    original = load(ROOT / "development/evaluation-before-temperature-screen/summary.json")
    assert original["policies"] == summary["policies"]
    print("PASS final temperature screening does not change the first recorded policy counts or scores", flush=True)
    print("LIMIT: synthetic finite-grid demonstration; not an industrial or statistically powered performance claim", flush=True)


if __name__ == "__main__":
    main()
