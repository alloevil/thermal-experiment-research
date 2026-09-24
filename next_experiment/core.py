"""Finite-ensemble thermal hypothesis comparison; no device execution."""

import copy
import math
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radiation"))
from model import HeatingModel, Parameters, np
from scipy.special import logsumexp, xlogy
from scipy.stats import chi2


NAMES = ("convection", "offset")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(value, name):
    require(type(value) in (int, float) and math.isfinite(value), f"{name}: finite number required")
    return float(value)


def numeric_array(value, name):
    def inspect(item):
        if isinstance(item, list):
            for child in item:
                inspect(child)
        else:
            number(item, name)
    inspect(value)
    array = np.asarray(value, dtype=float)
    require(array.size > 0 and np.isfinite(array).all(), f"{name}: empty/nonfinite array")
    return array


def example_case():
    def thermal(knots, levels, times, noise, enabled):
        return {"kind": "thermal", "enabled": enabled, "cost": 1, "sigma_K": noise,
                "knots_s": knots, "powers_W": [[level] * 3 for level in levels],
                "observations": [{"time_s": time, "position_m": .03} for time in times]}
    return {
        "schema": "thermal-next-experiment/1", "budget": 1,
        "max_predicted_temperature_K": 380,
        "assumptions": {"initial_temperature_K": 296.15, "independent_gaussian_noise": True,
                        "independent_reference_available": False},
        "priors": {"convection": .5, "offset": .5},
        "grid": {"convection": [1, 1.2, 1.4, 1.6], "offset_K": [0, -.3, -.6, -.9],
                 "gain": [.95, 1, 1.05], "capacity": [.95, 1, 1.05]},
        "experiments": {
            "initial": thermal([0, 20, 60], [0, .2, .2], [60], .25, False),
            "heat_low": thermal([0, 30, 120], [0, .2, .2], [60, 90, 120], .25, True),
            "heat_high": thermal([0, 45, 180], [0, .5, .5], [90, 135, 180], .25, True),
            "cooldown": thermal([0, 40, 80, 120, 180], [0, .4, .4, 0, 0], [120, 150, 180], .25, True),
            "reference": {"kind": "reference", "enabled": False, "cost": 2, "sigma_K": .15,
                          "duration_s": 30, "observations": [{"time_s": 30, "position_m": .03}]},
        },
    }


def validate_case(case):
    require(case["schema"] == "thermal-next-experiment/1", "Unsupported case schema")
    require(number(case["budget"], "budget") > 0, "Budget must be positive")
    require(296.15 <= number(case.get("max_predicted_temperature_K", 380), "temperature limit") <= 500,
            "Supported predicted temperature limit: 296.15–500K")
    assumptions = case["assumptions"]
    require(assumptions["initial_temperature_K"] == 296.15, "This thermal adapter requires a 296.15K equilibrium start")
    require(assumptions["independent_gaussian_noise"] is True, "Only stated independent Gaussian noise is supported")
    require(type(assumptions["independent_reference_available"]) is bool, "Reference availability must be boolean")
    prior = [number(case["priors"][name], name) for name in NAMES]
    require(all(value > 0 for value in prior) and math.isclose(sum(prior), 1), "Priors must be positive and sum to one")
    bounds = {"convection": (.5, 2), "offset_K": (-3, 3), "gain": (.8, 1.2), "capacity": (.8, 1.2)}
    for key, (lower, upper) in bounds.items():
        values = numeric_array(case["grid"][key], key)
        require(values.ndim == 1 and len(values) <= 15 and len(np.unique(values)) == len(values), "Grid must be a unique short vector")
        require(np.all((values >= lower) & (values <= upper)), f"Grid outside supported {key} range")
    grid = case["grid"]
    require((len(grid["convection"]) + len(grid["offset_K"])) * len(grid["gain"]) * len(grid["capacity"]) <= 512,
            "Prototype supports at most 512 particles")
    experiments = case["experiments"]
    require(isinstance(experiments, dict) and 1 <= len(experiments) <= 10, "Need 1–10 experiments")
    for name, experiment in experiments.items():
        require(isinstance(name, str) and name and len(name) <= 80, "Invalid experiment ID")
        require(type(experiment["enabled"]) is bool, "enabled must be boolean")
        require(number(experiment["cost"], "cost") > 0, "Positive experiment cost required")
        require(.05 <= number(experiment["sigma_K"], "sigma_K") <= 5, "Supported noise sigma: 0.05–5K")
        require(experiment["kind"] in {"thermal", "reference"}, "Unknown experiment kind")
        if experiment["kind"] == "thermal":
            times = numeric_array(experiment["knots_s"], "knots")
            powers = numeric_array(experiment["powers_W"], "powers")
            require(times.ndim == 1 and 2 <= len(times) <= 20 and times[0] == 0 and 0 < times[-1] <= 300
                    and np.all(np.diff(times) > 0), "Knots must increase from zero, duration <=300s")
            require(powers.shape == (len(times), 3) and np.all(powers[0] == 0) and powers.min() >= 0, "Need nonnegative three-zone powers starting at zero")
            maximum_gain = max(grid["gain"])
            require(powers.max() * maximum_gain <= 1 and np.max(abs(np.diff(powers, axis=0) / np.diff(times)[:, None])) * maximum_gain <= .015,
                    "Power/ramp violates declared 1W or 0.015W/s bound across gain grid")
            duration = times[-1]
        else:
            duration = number(experiment["duration_s"], "reference duration")
            require(0 < duration <= 300, "Invalid reference duration")
            require(not experiment["enabled"] or assumptions["independent_reference_available"], "Reference cannot be enabled without explicit independent-reference availability")
        require(1 <= len(experiment["observations"]) <= 12, "Need 1–12 measurements per experiment")
        coordinates = []
        for observation in experiment["observations"]:
            time = number(observation["time_s"], "observation time")
            position = number(observation["position_m"], "sensor position")
            require(0 <= time <= duration and .003 <= position <= .057, "Observation outside supported time/domain")
            coordinates.append((time, position))
        require(len(set(coordinates)) == len(coordinates), "Duplicate observation coordinates would double-count information")
    return case


def validate_records(case, data):
    records = data["records"]
    require(isinstance(records, list) and 1 <= len(records) <= 20, "Need 1–20 observation records")
    identifiers = set()
    for record in records:
        require(isinstance(record["id"], str) and record["id"] and record["id"] not in identifiers, "Record IDs must be nonempty and unique")
        identifiers.add(record["id"])
        require(record["experiment"] in case["experiments"], "Unknown observed experiment")
        experiment = case["experiments"][record["experiment"]]
        values = numeric_array(record["values_K"], "values_K")
        require(values.shape == (len(experiment["observations"]),), "Observation dimension mismatch")
        if experiment["kind"] == "thermal":
            require(np.all((values > 0) & (values <= 2000)), "Supported thermal observations: (0,2000] Kelvin")
        else:
            require(np.all(abs(values) <= 100), "Reference difference exceeds supported +/-100K")
    return records


def simulate(experiment, convection=1., offset=0., gain=1., capacity=1., cells=24, return_peak=False):
    if experiment["kind"] == "reference":
        values = np.full(len(experiment["observations"]), offset)
        return (values, 296.15) if return_peak else values
    base = Parameters()
    model = HeatingModel(cells, parameters=replace(base, convection=base.convection * convection,
                                                  heat_capacity=base.heat_capacity * capacity))
    output = model.solve(np.array(experiment["powers_W"]) * gain, knots=experiment["knots_s"],
                         sample_step=.5, rtol=1e-9, atol=1e-10)
    require(np.isfinite(output["temperature"]).all(), "Nonfinite solver output")
    stored = model.cell_capacity * (output["temperature"] - base.ambient).sum(axis=1)
    ledger = output["ledger"]
    require(np.max(abs(stored - ledger[:, 0] + ledger[:, 1] + ledger[:, 2])) < 1e-4, "Energy balance failed")
    values = []
    for observation in experiment["observations"]:
        spatial = np.array([np.interp(observation["position_m"], model.coordinates, row) for row in output["temperature"]])
        values.append(np.interp(observation["time_s"], output["time"], spatial) + offset)
    values = np.array(values)
    return (values, float(output["temperature"].max())) if return_peak else values


class ExperimentBank:
    def __init__(self, case):
        self.case = copy.deepcopy(validate_case(case))
        grid = case["grid"]
        self.particles, self.labels, logpriors = [], [], []
        for model_index, name in enumerate(NAMES):
            values = grid["convection"] if name == "convection" else grid["offset_K"]
            total = len(values) * len(grid["gain"]) * len(grid["capacity"])
            for value in values:
                for gain in grid["gain"]:
                    for capacity in grid["capacity"]:
                        self.particles.append({"convection": value if name == "convection" else 1.,
                                               "offset": value if name == "offset" else 0., "gain": gain, "capacity": capacity})
                        self.labels.append(model_index)
                        logpriors.append(np.log(case["priors"][name] / total))
        self.labels = np.array(self.labels)
        self.logprior = np.array(logpriors)
        self.predictions = {}
        self.peak_temperatures = {}
        self.excluded = []
        self.solve_calls = 0

    def predict(self, name):
        if name not in self.predictions:
            experiment = self.case["experiments"][name]
            cache, predicted, peaks = {}, [], []
            for particle in self.particles:
                key = (particle["convection"], particle["gain"], particle["capacity"])
                if experiment["kind"] == "reference":
                    predicted.append(np.full(len(experiment["observations"]), particle["offset"]))
                    peaks.append(296.15)
                    continue
                if key not in cache:
                    cache[key] = simulate(experiment, convection=key[0], gain=key[1], capacity=key[2], return_peak=True)
                    self.solve_calls += 1
                predicted.append(cache[key][0] + particle["offset"])
                peaks.append(cache[key][1])
            self.predictions[name] = np.array(predicted)
            self.peak_temperatures[name] = max(peaks)
        return self.predictions[name]

    def posterior(self, observations):
        records = validate_records(self.case, observations)
        logweight = self.logprior.copy()
        squared = np.zeros(len(self.labels))
        incompatible_records = []
        dimensions = 0
        for record in records:
            experiment = self.case["experiments"][record["experiment"]]
            residual = (self.predict(record["experiment"]) - record["values_K"]) / experiment["sigma_K"]
            contribution = np.sum(residual**2, axis=1)
            dimensions += residual.shape[1]
            squared += contribution
            logweight -= .5 * contribution
            if all(chi2.sf(np.min(contribution[self.labels == index]), residual.shape[1]) < .001 for index in range(2)):
                incompatible_records.append(record["id"])
        logweight -= logsumexp(logweight)
        weights = np.exp(logweight)
        weights /= weights.sum()
        probabilities = np.array([weights[self.labels == index].sum() for index in range(2)])
        probabilities /= probabilities.sum()
        fit_tail = [float(chi2.sf(np.min(squared[self.labels == index]), dimensions)) for index in range(2)]
        status = "unsupported" if max(fit_tail) < .001 or incompatible_records else (
            "supported_hypothesis" if probabilities.max() >= .95 else "ambiguous")
        summary = {"status": status, "model_probability": dict(zip(NAMES, probabilities.tolist(), strict=True)),
                   "best_grid_fit_tail_probability": dict(zip(NAMES, fit_tail, strict=True)),
                   "incompatible_records": incompatible_records, "particle_ess": float(1 / np.sum(weights**2)),
                   "particle_count": len(weights), "records": len(records),
                   "supported": NAMES[int(probabilities.argmax())] if status == "supported_hypothesis" else None,
                   "meaning": "Relative support within two finite candidate grids, not proven root cause or calibrated confidence.",
                   "engineering_release": "not_supported"}
        return summary, weights

    def score_experiments(self, weights, seed=20261001, samples=128):
        generator = np.random.default_rng(seed)
        chosen = generator.choice(len(weights), size=samples, p=weights)
        max_dimensions = max(len(item["observations"]) for item in self.case["experiments"].values())
        noise = generator.normal(size=(samples, max_dimensions))
        labels = self.labels
        probabilities = np.array([weights[labels == index].sum() for index in range(2)])
        prior_entropy = float(-np.sum(xlogy(probabilities, probabilities)))
        logweights = np.log(np.maximum(weights, np.finfo(float).tiny))
        options = []
        self.excluded = []
        for name, experiment in self.case["experiments"].items():
            if not experiment["enabled"] or experiment["cost"] > self.case["budget"]:
                continue
            predictions = self.predict(name)
            peak = self.peak_temperatures.get(name)
            if peak is not None and peak > self.case.get("max_predicted_temperature_K", 380):
                self.excluded.append({"experiment": name, "reason": "finite_grid_predicted_temperature_limit",
                                      "predicted_peak_K": peak})
                continue
            sigma, dimensions = experiment["sigma_K"], predictions.shape[1]
            observed = predictions[chosen] + sigma * noise[:, :dimensions]
            likelihood = -.5 * np.sum(((observed[:, None, :] - predictions[None, :, :]) / sigma)**2, axis=2)
            posterior = likelihood + logweights
            posterior -= logsumexp(posterior, axis=1, keepdims=True)
            posterior_probabilities = np.column_stack([np.exp(logsumexp(posterior[:, labels == index], axis=1)) for index in range(2)])
            entropies = -np.sum(xlogy(posterior_probabilities, posterior_probabilities), axis=1)
            utilities = prior_entropy - entropies
            summaries, means, variances = {}, [], []
            for index, model_name in enumerate(NAMES):
                mask = labels == index
                conditional = weights[mask] / weights[mask].sum() if weights[mask].sum() > 1e-300 else np.full(mask.sum(), 1 / mask.sum())
                mean = np.sum(predictions[mask] * conditional[:, None], axis=0)
                variance = np.sum((predictions[mask] - mean)**2 * conditional[:, None], axis=0) + sigma**2
                draw_generator = np.random.default_rng(seed + index)
                particle_ids = draw_generator.choice(mask.sum(), 1024, p=conditional)
                draws = predictions[mask][particle_ids] + sigma * draw_generator.normal(size=(1024, dimensions))
                summaries[model_name] = {"mean_K": mean.tolist(), "predictive_p05_K": np.quantile(draws, .05, axis=0).tolist(),
                                        "predictive_p95_K": np.quantile(draws, .95, axis=0).tolist()}
                means.append(mean)
                variances.append(variance)
            separation = (means[0] - means[1])**2 / (variances[0] + variances[1])
            options.append({"experiment": name, "expected_information_gain_nats": float(utilities.mean()),
                            "monte_carlo_standard_error_nats": float(utilities.std(ddof=1) / np.sqrt(samples)),
                            "mean_separation_score": float(separation.sum()), "most_separating_observation": int(separation.argmax()),
                            "cost": experiment["cost"], "details": copy.deepcopy(experiment), "predictions": summaries})
            options[-1]["finite_grid_peak_K"] = peak
        return sorted(options, key=lambda item: (-item["expected_information_gain_nats"], item["experiment"]))

    def recommend(self, observations):
        summary, weights = self.posterior(observations)
        result = {"posterior": summary, "recommendation": None, "options": [], "status": summary["status"],
                  "engineering_release": "not_supported", "requirements": [
                      "Each experiment restarts from independently confirmed 296.15K equilibrium.",
                      "User must approve inputs and instrument/reference validity; modeled constraints are not safety clearance.",
                      "Finite-grid predictions and assumed independent noise may be wrong; other causes are not excluded."]}
        if summary["status"] == "unsupported":
            result["reason"] = "Both candidate grids cannot adequately explain at least one record or the joint data; revise models/measurement assumptions."
            return result
        if summary["status"] == "supported_hypothesis":
            result["reason"] = "Existing data already give >=0.95 support within the candidate set; no additional experiment requested."
            return result
        options = self.score_experiments(weights)
        result["options"] = options
        result["excluded_experiments"] = copy.deepcopy(self.excluded)
        if not options:
            result.update(status="no_available_experiment", reason="No enabled experiment meets budget and finite-grid temperature screen; no implicit reference assumed.")
        elif options[0]["expected_information_gain_nats"] < .01:
            result.update(status="not_distinguishable", reason="Allowed experiments provide <0.01 nat estimated model-label information; do not force a recommendation.")
        else:
            result.update(status="experiment_recommended", recommendation=options[0]["experiment"],
                          reason="Highest estimated model-label information among enabled budget-feasible experiments; estimate is not a performance guarantee.")
        return result


def add_measurement(case, observations, measurement):
    validate_case(case)
    validate_records(case, observations)
    require(measurement["experiment"] in case["experiments"], "Unknown measurement experiment")
    experiment = case["experiments"][measurement["experiment"]]
    require(experiment["enabled"] and experiment["cost"] <= case["budget"], "New experiment is disabled or outside current budget")
    updated = {"records": copy.deepcopy(observations["records"]) + [copy.deepcopy(measurement)]}
    validate_records(case, updated)
    return updated


def card(result):
    lines = ["# 下一次试验建议", "", f"状态：`{result['status']}`", "", result["reason"], "",
             "## 当前候选支持（不是根因确认）", ""]
    lines += [f"- {name}: {probability:.3%}" for name, probability in result["posterior"]["model_probability"].items()]
    if result["recommendation"]:
        selected = next(item for item in result["options"] if item["experiment"] == result["recommendation"])
        details = selected["details"]
        lines += ["", f"## 建议：{selected['experiment']}", "",
                  f"预期信息增益 {selected['expected_information_gain_nats']:.4f} nat；蒙特卡洛标准误差 {selected['monte_carlo_standard_error_nats']:.4f}。",
                  f"声明成本 {selected['cost']} 单位；噪声假设 σ={details['sigma_K']} K。",
                  f"有限参数网格与离散时间预测最高温度：{selected['finite_grid_peak_K']} K（不是连续或实物安全保证）。"]
        if details["kind"] == "thermal":
            lines += ["", "每次从 296.15K 均温重新开始；以下为声明的吸收功率指令，非设备控制命令。", "", "|时刻 s|三区功率 W|", "|---|---|"]
            lines += [f"|{time}|{power}|" for time, power in zip(details["knots_s"], details["powers_W"], strict=True)]
        else:
            lines += ["", "使用经独立确认有效的温度参考，测量传感器读数减参考读数（K差值）；不能用同一有偏通道自证。"]
        lines += ["", "|观测|时间 s|位置 m|散热解释均值/5–95% K|零偏解释均值/5–95% K|", "|---|---|---|---|---|"]
        for index, observation in enumerate(details["observations"]):
            prediction = selected["predictions"]
            descriptions = [f"{prediction[name]['mean_K'][index]:.3f} / [{prediction[name]['predictive_p05_K'][index]:.3f}, {prediction[name]['predictive_p95_K'][index]:.3f}]" for name in NAMES]
            lines.append(f"|{index + 1}|{observation['time_s']}|{observation['position_m']}|{descriptions[0]}|{descriptions[1]}|")
        lines += ["", f"按标准化预测分离度最值得关注的是第 {selected['most_separating_observation'] + 1} 个观测；不要只读取这一点更新，其余测量同样要保留。"]
    lines += ["", "## 限制", "", "区间来自有限参数后验和测量噪声的模拟，不是经实物校准的置信界。"]
    lines += [f"- {item}" for item in result["requirements"]]
    lines += ["- 不支持工程放行，不自动执行试验。", ""]
    return "\n".join(lines)
