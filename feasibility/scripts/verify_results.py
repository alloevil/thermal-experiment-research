import hashlib
import json
import math
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def reject_constant(value):
    raise ValueError(f"Non-standard JSON constant: {value}")


def read_json(path):
    return json.loads(path.read_text(), parse_constant=reject_constant)


def main():
    for item in read_json(ROOT / "upstream/manifest.json"):
        assert hashlib.sha256((ROOT / item["file"]).read_bytes()).hexdigest() == item["sha256"]
    print("PASS upstream commit-pinned source hashes")
    for script in (ROOT / "scripts").glob("*.py"):
        compile(script.read_text(), str(script), "exec")
    print("PASS experiment script syntax")
    heat = read_json(ROOT / "results/upstream-heat.json")
    assert heat["status"] == "PASS" and len(heat["tests"]) == 3
    assert all(item["status"] == "PASS" for item in heat["tests"])
    print("PASS original heat example and 3 selected upstream tests")
    bo = read_json(ROOT / "results/upstream-botorch.json")
    assert bo["status"] == "PASS" and len(bo["recommendations"]) == 2
    assert all(item["observations"] == 20 for item in bo["recommendations"])
    assert all(item["candidate"][0][-1] == 1.0 for item in bo["recommendations"])
    assert all(item["status"] == "PASS" for item in bo["cells"])
    assert len(bo["transforms"]) == 1 and "%pip" in bo["transforms"][0]["original"]
    print(f"PASS {len(bo['cells'])} upstream notebook code cells; 2 target-fidelity recommendations")
    config = read_json(ROOT / "results/thermal-config.json")
    records = [json.loads(line, parse_constant=reject_constant) for line in
               (ROOT / "results/thermal-raw.jsonl").read_text().splitlines()]
    identities = {(item["case"], item["resolution"], item["repeat"]) for item in records}
    expected = {(case_index, resolution, repeat) for case_index in range(len(config["cases"]))
                for resolution in config["resolutions"] for repeat in range(config["repeats"])}
    assert identities == expected and len(records) == len(expected) == 160
    assert Counter(item["resolution"] for item in records) == {16: 40, 32: 40, 64: 40, 128: 40}
    for item in records:
        assert item["amplitudes"] == config["cases"][item["case"]]
        assert item["mean_drift_K"] < 1e-8
        assert item["temporal_max_error_K"] < min(1e-6, item["spatial_max_error_K"] * 0.01)
        assert abs(item["final_nonuniformity_std_K"] - item["semidiscrete_nonuniformity_std_K"]) < 1e-6
        variance = 0.0
        for amplitude, (mode_x, mode_y) in zip(item["amplitudes"], config["modes"], strict=True):
            resolution = item["resolution"]
            decay = 4 * config["diffusivity_m2_per_s"] * resolution**2 * (
                math.sin(math.pi * mode_x / (2 * resolution)) ** 2
                + math.sin(math.pi * mode_y / (2 * resolution)) ** 2
            )
            variance += amplitude**2 * math.exp(-2 * decay * config["final_time_s"]) / 4
        assert abs(item["final_nonuniformity_std_K"] - math.sqrt(variance)) < 1e-6
        assert item["wall_seconds"] > 0 and item["cpu_seconds"] > 0
    print("PASS 160 unique paired measurements, fixed inputs and time-error/conservation gates")
    print("PASS temperature standard deviation against independently evaluated modal variance")
    summary = read_json(ROOT / "results/thermal-summary.json")
    assert summary["status"] == "PASS"
    assert all(1.5 < item["order"] < 2.5 for item in summary["spatial_convergence_orders"])
    assert 1.5 < summary["extra_refinement_order_128_to_256"] < 2.5
    assert [item["resolution"] for item in summary["tight_tolerance_checks"]] == [128, 256]
    print("PASS spatial convergence and 100x tighter time tolerances at 128/256")
    environment = read_json(ROOT / "results/environment.json")
    assert environment["protocol_sha256"] == hashlib.sha256((ROOT / "protocol.md").read_bytes()).hexdigest()
    print("PASS measurement protocol unchanged since preregistration")
    artifacts = []
    for directory in ["results", "logs", "scripts"]:
        for target in sorted((ROOT / directory).glob("*")):
            if target.is_file() and target.name not in {"verification.log", "artifact-manifest.json"}:
                artifacts.append({"file": str(target.relative_to(ROOT)),
                                  "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    for filename in ["requirements.in", "requirements.lock", "protocol.md", "RESULTS.md", "RUNBOOK.md"]:
        artifacts.append({"file": filename, "sha256": hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()})
    (ROOT / "results/artifact-manifest.json").write_text(json.dumps(artifacts, indent=2) + "\n")
    print(f"PASS recorded {len(artifacts)} local artifact hashes")
    print("NOT CLAIMED: full upstream CI, controlled optimizer superiority, furnace accuracy or industrial validation")


if __name__ == "__main__":
    main()
