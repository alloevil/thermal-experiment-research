import argparse
import hashlib
import io
import json
import math
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath

import numpy as np


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def strict_json(payload):
    def pairs(entries):
        result = {}
        for key, value in entries:
            require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid(value):
        raise EvidenceError(f"Non-finite JSON number: {value}")

    def floating(value):
        converted = float(value)
        require(math.isfinite(converted), f"Non-finite JSON number: {value}")
        return converted

    return json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid, parse_float=floating)


def scalar(value, name):
    require(type(value) in (int, float) and math.isfinite(value), f"Invalid finite number: {name}")
    return value


def flag(value, name):
    require(type(value) is bool, f"Expected boolean: {name}")
    return value


def close(actual, expected, name):
    require(math.isclose(float(actual), scalar(expected, name), rel_tol=1e-9, abs_tol=1e-9), f"Inconsistent {name}")


def safe_path(root, relative):
    require(isinstance(relative, str) and relative and "\\" not in relative, "Invalid relative path")
    parsed = PurePosixPath(relative)
    require(not parsed.is_absolute() and '..' not in parsed.parts and str(parsed) == relative, f"Unsafe path: {relative}")
    current = root
    for component in parsed.parts:
        current = current / component
        require(not current.is_symlink(), f"Symbolic link not allowed: {relative}")
    require(current.is_file(), f"Missing evidence: {relative}")
    return current


class Snapshot:
    def __init__(self, root, expected_hash):
        self.root = Path(root).resolve(strict=True)
        require(re.fullmatch(r"[0-9a-f]{64}", expected_hash) is not None, "Expected lowercase SHA-256")
        raw = safe_path(self.root, "results/artifact-manifest.json").read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected_hash, "Manifest SHA-256 mismatch")
        self.manifest_hash = expected_hash
        entries = strict_json(raw)
        require(isinstance(entries, list) and entries, "Manifest must be a nonempty list")
        self.hashes = {}
        for entry in entries:
            name, checksum = entry["file"], entry["sha256"]
            require(isinstance(name, str) and name not in self.hashes, "Duplicate/invalid manifest path")
            require(isinstance(checksum, str) and re.fullmatch(r"[0-9a-f]{64}", checksum), "Invalid artifact hash")
            self.hashes[name] = checksum
            self.bytes(name)

    def bytes(self, name):
        require(name in self.hashes, f"Evidence not in manifest: {name}")
        raw = safe_path(self.root, name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == self.hashes[name], f"Artifact SHA-256 mismatch: {name}")
        return raw

    def json(self, name):
        return strict_json(self.bytes(name))

    def arrays(self, name):
        with np.load(io.BytesIO(self.bytes(name)), allow_pickle=False) as archive:
            result = {key: archive[key] for key in archive.files}
        for key, array in result.items():
            require(array.dtype.kind in "fiu" and np.isfinite(array).all(), f"Invalid numeric array: {name}/{key}")
        return result


MISSING = [
    "reference_traceability_and_systematic_error_bound",
    "independent_thermal_equilibrium_evidence",
    "correction_valid_temperature_range_and_expiry",
    "temperature_dependent_drift_bound",
    "hardware_validation",
]


def residual_result(residual, success=True):
    require(residual.shape == (48, 3) and np.isfinite(residual).all(), "Residuals must be finite with shape (48,3)")
    flag(success, "fit.success")
    rmse = float(np.sqrt(np.mean(residual**2)))
    mean = float(np.max(abs(residual.mean(axis=0))))
    reasons = []
    if not success:
        reasons.append("fit_not_converged")
    if rmse > .2:
        reasons.append("residual_rmse_above_0.2K")
    if mean > .2:
        reasons.append("sensor_mean_residual_above_0.2K")
    return {"alarm": bool(reasons), "reasons": reasons, "rmse_K": rmse, "max_sensor_mean_residual_K": mean}


def observable_record(identifier, branch, success, training, diagnostic, offset):
    alarmed = training["alarm"] or diagnostic["alarm"]
    return {
        "id": identifier, "branch": branch, "fit_converged": success,
        "training": training, "diagnostic": diagnostic, "combined_alarm": alarmed,
        "offset_applied": branch == "corrected",
        "anchor_samples": offset["samples"],
        "offset_K": offset["offset_K"], "offset_mean_standard_error_K": offset["mean_standard_error_K"],
        "standard_error_scope": "Random sampling precision only; excludes systematic reference error and drift.",
        "review_reasons": (["observed_residual_alarm"] if alarmed else ["no_residual_alarm_is_not_validation"])
                          + ["missing_reference_and_applicability_evidence", "synthetic_study_only"],
        "engineering_release": "not_supported",
    }


def build_report(stage, manifest_sha256):
    snapshot = Snapshot(stage, manifest_sha256)
    config = snapshot.json("results/config.json")
    scenarios = ["clean", "stable", "reference_bias", "thermal_drift"]
    require(config["scenarios"] == scenarios and len(config["objects"]) == 2 and config["replicates"] == 2,
            "Only the frozen reference-correction 32-branch study is supported")
    require(config["anchor_samples"] == 10, "Expected ten anchor samples")
    require(set(config["hashes"]) == {
        "protocol.md", "run.py", "correction.py", "model_mismatch/experiment.py",
        "calibration/effective.py", "calibration/fit_and_control.py", "radiation/model.py",
        "radiation/results/experiment.json", "feasibility/requirements.lock",
    }, "Incomplete or unsupported dependency inventory")
    for name, checksum in config["hashes"].items():
        dependency_root = snapshot.root if "/" not in name else snapshot.root.parent
        raw = safe_path(dependency_root, name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == checksum, f"Dependency changed: {name}")
    operational, retrospective = [], []
    for object_index in range(2):
        for replicate in range(2):
            for scenario in scenarios:
                parent = f"results/object-{object_index}/noise-{replicate}-{scenario}"
                offset = snapshot.json(f"{parent}/offset.json")
                readings = snapshot.arrays(f"{parent}/readings.npz")
                require(readings["anchor"].shape == (10, 3) and readings["reference"].shape == (10,), "Invalid anchor shape")
                require(np.min(readings["anchor"]) > 0 and np.min(readings["reference"]) > 0, "Invalid Kelvin readings")
                differences = readings["anchor"] - readings["reference"][:, None]
                require(type(offset["samples"]) is int and offset["samples"] == 10, "Invalid sample count")
                for name, values in [("offset_K", differences.mean(axis=0)),
                                     ("difference_sample_std_K", differences.std(axis=0, ddof=1)),
                                     ("mean_standard_error_K", differences.std(axis=0, ddof=1) / np.sqrt(10))]:
                    require(len(offset[name]) == 3, "Invalid offset vector")
                    for actual, expected in zip(values, offset[name], strict=True):
                        close(actual, expected, name)
                for quantity in ["train", "diag"]:
                    raw, corrected = readings[f"raw_{quantity}"], readings[f"corrected_{quantity}"]
                    require(raw.shape == corrected.shape == (48, 3) and min(raw.min(), corrected.min()) > 0, "Invalid observations")
                    require(np.allclose(corrected, raw - differences.mean(axis=0), rtol=0, atol=1e-9), "Invalid offset application")
                for branch in ["raw", "corrected"]:
                    location = f"{parent}/{branch}"
                    case = snapshot.json(f"{location}/case.json")
                    fit, alarm = snapshot.json(f"{location}/fit.json"), snapshot.json(f"{location}/alarm.json")
                    require(case["key"] == location.removeprefix("results/") and case["branch"] == branch
                            and case["object"] == object_index and case["replicate"] == replicate
                            and case["scenario"] == scenario, "Case identity mismatch")
                    for name, data, filename in [("fit", fit, f"{location}/fit.json"),
                                                 ("alarm", alarm, f"{location}/alarm.json"),
                                                 ("offset", offset, f"{parent}/offset.json")]:
                        require(case[name] == data and case[f"{name}_hash"] == snapshot.hashes[filename], f"Inconsistent frozen {name}")
                    success = flag(fit["success"], "fit.success")
                    residuals = snapshot.arrays(f"{location}/residuals.npz")
                    training = residual_result(residuals["training"], success)
                    diagnostic = residual_result(residuals["diagnostic"])
                    close(training["rmse_K"], fit["train_rmse_K"], "fit residual RMSE")
                    for name, computed in [("training", training), ("diagnostic", diagnostic)]:
                        require(flag(alarm[name]["alarm"], "residual alarm") == computed["alarm"]
                                and alarm[name]["reasons"] == computed["reasons"], "Inconsistent alarm decision")
                        for quantity in ["rmse_K", "max_sensor_mean_residual_K"]:
                            close(computed[quantity], alarm[name][quantity], quantity)
                    require(flag(alarm["combined"], "combined alarm") == (training["alarm"] or diagnostic["alarm"]), "Inconsistent combined alarm")
                    identifier = f"case-{len(operational) + 1:03d}"
                    operational.append(observable_record(identifier, branch, success, training, diagnostic, offset))
                    truth = snapshot.arrays(f"results/object-{object_index}/truth.npz")
                    prediction = snapshot.arrays(f"{location}/prediction.npz")
                    require(truth["temperature"].shape == prediction["temperature"].shape == (721, 96), "Invalid evaluation shape")
                    require(np.array_equal(truth["time"], prediction["time"]), "Evaluation timestamps mismatch")
                    rmse = float(np.sqrt(np.mean((truth["temperature"] - prediction["temperature"])**2)))
                    final = float(abs(truth["temperature"][-1].mean() - prediction["temperature"][-1].mean()))
                    close(rmse, case["score"]["rmse_K"], "hidden RMSE")
                    close(final, case["score"]["final_mean_error_K"], "hidden final error")
                    bad = rmse > .5 or final > 1
                    require(flag(case["score"]["inadequate"], "prediction label") == bad, "Inconsistent hidden prediction label")
                    retrospective.append({"id": identifier, "source_case": case["key"], "scenario": scenario,
                                          "branch": branch, "object": object_index, "replicate": replicate,
                                          "field_rmse_K": rmse, "final_mean_error_K": final,
                                          "inadequate_prediction": bad, "missed_by_residual_rule": bad and not alarm["combined"]})
    source_verification = snapshot.json("results/verification.json")
    return {
        "schema_version": "reference-correction-evidence/1", "study_kind": "synthetic_research",
        "engineering_release": "not_supported",
        "integrity": {"manifest_sha256": snapshot.manifest_hash, "verified_artifacts": len(snapshot.hashes),
                      "meaning": "Matches caller-selected snapshot, not authenticity or metrological traceability."},
        "validation_scope": {"performed": ["artifact and dependency hashing", "offset arithmetic", "saved residual decision recomputation", "saved field error recomputation"],
                             "not_performed": ["ODE replay", "parameter refitting", "independent physics validation", "hardware or reference certification"],
                             "source_verifier_reported_status": source_verification["status"]},
        "missing_evidence": MISSING.copy(), "observable_review": operational,
        "retrospective_evaluation": {"use": "Simulation-only hindsight; never used by observable review reasons.", "cases": retrospective},
        "counts": {"branches": len(operational), "alarmed": sum(item["combined_alarm"] for item in operational),
                   "retrospective_inadequate": sum(item["inadequate_prediction"] for item in retrospective),
                   "retrospective_missed": sum(item["missed_by_residual_rule"] for item in retrospective)},
    }


def markdown(report):
    lines = ["# 参考校正证据说明", "", "**用途：合成研究复核。不支持工程放行。**", "",
             f"快照摘要：`{report['integrity']['manifest_sha256']}`",
             f"核对文件：{report['integrity']['verified_artifacts']}；分支：{report['counts']['branches']}。",
             "哈希一致不等于参考真实、物理有效或计量溯源；本命令没有重跑求解器。", "",
             "## 仍缺少的证据", ""]
    lines.extend(f"- `{item}`" for item in report["missing_evidence"])
    lines += ["", "## 可观测复核（不使用隐藏真值）", "",
              "|编号|分支|拟合收敛|残差告警|建议|", "|---|---|---|---|---|"]
    for item in report["observable_review"]:
        lines.append(f"|{item['id']}|{item['branch']}|{item['fit_converged']}|{item['combined_alarm']}|复核参考及适用条件，不放行|")
    lines += ["", "均值标准误差仅描述随机采样精度，不含参考系统误差或漂移。", "",
              "## 回顾性评价（仅仿真端可知）", "",
              "本节含隐藏真值，不能作为现场诊断功能。跨分支共享对象与观测，不是独立设备样本。", "",
              "|编号|合成情形|隐藏场RMSE K|预测不足|残差漏报|", "|---|---|---:|---|---|"]
    for item in report["retrospective_evaluation"]["cases"]:
        lines.append(f"|{item['id']}|{item['scenario']}|{item['field_rmse_K']:.6f}|{item['inadequate_prediction']}|{item['missed_by_residual_rule']}|")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only evidence report for the frozen reference-correction study; never authorizes engineering release.")
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.stage, args.manifest_sha256)
        rendered = markdown(report) if args.format == "markdown" else json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    except (ValueError, OSError, KeyError, TypeError, IndexError, zipfile.BadZipFile, EOFError) as error:
        print(f"Evidence report rejected: {error}", file=sys.stderr)
        return 2
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
