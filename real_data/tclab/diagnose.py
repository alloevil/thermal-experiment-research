"""Read-only interval-aware excitation checks for two-heater Celsius/percent CSVs."""

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path


HEADERS = ["Time (sec)", "Heater 1 (%)", "Heater 2 (%)", "Temperature 1 (degC)", "Temperature 2 (degC)"]
SETPOINTS = ["Set Point 1 (degC)", "Set Point 2 (degC)"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_record(path):
    payload = Path(path).read_bytes()
    reader = csv.reader(io.StringIO(payload.decode("utf-8-sig")), strict=True)
    header = next(reader, None)
    require(header is not None, "Empty file: expected an explicit units header")
    header = [item.strip() for item in header]
    require(header in [HEADERS, HEADERS + SETPOINTS], "Expected ordered Time (sec), Heater 1/2 (%), Temperature 1/2 (degC); optional two setpoints")
    rows = []
    for line, fields in enumerate(reader, 2):
        if not fields:
            continue
        require(len(fields) == len(header), f"Line {line}: wrong column count")
        try:
            values = [float(field) for field in fields]
        except ValueError as error:
            raise ValueError(f"Line {line}: all fields must be numeric") from error
        require(all(math.isfinite(value) for value in values), f"Line {line}: non-finite value")
        require(values[0] >= 0, f"Line {line}: negative time")
        require(not rows or values[0] > rows[-1][0], f"Line {line}: time must strictly increase")
        require(all(0 <= value <= 100 for value in values[1:3]), f"Line {line}: heater input outside 0–100 percent")
        require(all(value > -273.15 for value in values[3:]), f"Line {line}: invalid Celsius absolute temperature")
        rows.append(values)
    require(len(rows) >= 2, "At least two measurement rows are required")
    return rows, {"file_name": Path(path).name, "sha256": hashlib.sha256(payload).hexdigest(),
                  "rows_in_file": len(rows), "columns": header}


def analyze(path, before_seconds=None):
    rows, provenance = read_record(path)
    if before_seconds is not None:
        require(math.isfinite(before_seconds) and before_seconds > 0, "before-seconds must be finite and positive")
        rows = [row for row in rows if row[0] < before_seconds]
    require(len(rows) >= 2, "Selected prefix must contain at least two rows")
    durations = [right[0] - left[0] for left, right in zip(rows, rows[1:])]
    channels = []
    for channel in [1, 2]:
        applied = [row[channel] for row in rows[:-1]]
        last_unobserved = rows[-1][channel]
        active_seconds = math.fsum(duration for value, duration in zip(applied, durations) if value != 0)
        integral = math.fsum(value * duration for value, duration in zip(applied, durations))
        require(math.isfinite(active_seconds) and math.isfinite(integral), "Input/time integral overflows supported numeric range")
        no_information = all(value == 0 for value in applied)
        changed_at_last = last_unobserved != applied[-1]
        evidence = {"parameter": f"alpha{channel}", "heater": channel,
                    "status": "no_input_information" if no_information else "not_ruled_out_by_zero_input_check",
                    "observed_min_percent": min(applied), "observed_max_percent": max(applied),
                    "nonzero_intervals": sum(value != 0 for value in applied),
                    "nonzero_duration_s": active_seconds, "input_integral_percent_seconds": integral,
                    "observed_input_changes": sum(left != right for left, right in zip(applied, applied[1:])),
                    "last_row_input_percent": last_unobserved, "last_row_changed_without_followup": changed_at_last,
                    "constant_nonzero_input": not no_information and len(set(applied)) == 1,
                    "explanation": (
                        f"Q{channel}=0 on every observed interval, so alpha{channel}*Q{channel} is zero; this window cannot estimate alpha{channel} in the stated model."
                        if no_information else "Nonzero input is present. This check does not establish parameter identifiability, precision, or sufficient excitation."),
                    "next_step": (
                        "Obtain temperature observations after the terminal command, or plan a separately approved independent excitation for this channel; do not invent an estimated gain."
                        if no_information and changed_at_last else
                        "If this gain is an estimation target, obtain independently approved excitation of this channel with follow-up observations, or independent gain-calibration evidence."
                        if no_information else
                        "Check model sensitivities, measurement noise and permitted input variation before claiming the gain is estimable.")}
        channels.append(evidence)
    missing = [channel["parameter"] for channel in channels if channel["status"] == "no_input_information"]
    identical = all(row[1] == row[2] for row in rows[:-1])
    return {
        "schema": "tclab-excitation-diagnosis/1", "source": provenance,
        "selection": {"before_seconds_exclusive": before_seconds, "rows_used": len(rows),
                      "intervals_used": len(durations), "start_s": rows[0][0], "last_observation_s": rows[-1][0],
                      "duration_s": rows[-1][0] - rows[0][0]},
        "model_scope": "APMonitor-style two-node heating model; alpha1*Q1 and alpha2*Q2 input terms. Not a generic device identifiability analysis.",
        "timing_assumption": "Temperature measured at t_i, then Q_i applied on [t_i,t_(i+1)); last input has no follow-up observation.",
        "status": "missing_excitation" if missing else "no_zero_input_obstruction_found",
        "parameters_without_input_information": missing, "channels": channels,
        "identical_observed_inputs": identical,
        "input_diversity_note": "Identical channel commands lack independent input variation; this alone does not prove non-identifiability." if identical else
                                "Commands differ somewhere; that alone does not prove useful independent excitation.",
        "initial_measurements_C": rows[0][3:5], "initial_T1_minus_T2_C": rows[0][3] - rows[0][4],
        "initial_state_note": "Different initial temperatures are not proof of sensor bias, thermal equilibrium, or ambient temperature. Setpoints are not ambient measurements.",
        "requirements_before_followup": ["Confirm units and measurement/actuation timing.",
                                         "Specify the target parameter and independently approved heater/channel limits.",
                                         "Approve temperature/ramp limits and observation duration; none are inferred from this log.",
                                         "Record the other heater's input and starting conditions.",
                                         "Establish sensor/reference validity and noise; record subsequent observations."],
        "engineering_release": "not_supported", "hardware_action": "none",
    }


def markdown(report):
    selection = report["selection"]
    lines = ["# 双加热器测试记录诊断", "", f"状态：`{report['status']}`", "",
             f"使用 {selection['rows_used']} 行、{selection['intervals_used']} 个区间，覆盖 {selection['start_s']:.6f}–{selection['last_observation_s']:.6f} 秒。",
             "最后一行指令没有后续观测覆盖，不算已完成激励。输入积分单位为百分比·秒，不是热量。", "",
             "|参数|诊断|已观测输入范围 %|非零时长 s|已观测指令变化数|", "|---|---|---:|---:|---:|"]
    for channel in report["channels"]:
        label = "严格零输入：本窗口无法估计" if channel["status"] == "no_input_information" else "有非零输入：未证明可辨识"
        lines.append(f"|{channel['parameter']}|{label}|{channel['observed_min_percent']:g}–{channel['observed_max_percent']:g}|{channel['nonzero_duration_s']:.6f}|{channel['observed_input_changes']}|")
    lines += ["", "## 下一步需要补什么", ""]
    for channel in report["channels"]:
        if channel["status"] == "no_input_information":
            lines.append(f"- **若目标包含 alpha{channel['heater']}：** 该参数只出现在 alpha{channel['heater']} × Q{channel['heater']} 项，而本窗口该路已观测区间输入全部为零。需要该路经操作者批准的独立输入变化及后续温度观测，或独立增益标定证据。")
        if channel["last_row_changed_without_followup"]:
            lines.append(f"- 第 {channel['heater']} 路在最后一行变为 {channel['last_row_input_percent']:g}%；缺少其生效后的测量，不能把这一行当成已经验证的激励。")
        if channel["constant_nonzero_input"]:
            lines.append(f"- 第 {channel['heater']} 路在已观测区间内恒定非零；动态响应可能仍含信息，但本检查没有证明参数精度。")
    if not report["parameters_without_input_information"]:
        lines.append("- 没有发现严格零输入障碍；这不是‘所有参数可辨识’结论。下一步应核对参数灵敏度、测量噪声和模型范围，而非自动再做试验。")
    if report["identical_observed_inputs"]:
        lines.append("- 两路已观测输入完全相同：缺少独立输入变化，但仅此不能证明参数不可辨识。")
    lines += ["", "## 执行前仍需确认", "",
              "- 输入单位、测温与施加指令的先后时序。",
              "- 目标参数及操作者批准的输入幅值、变化率、温度上限和观测时长。",
              "- 其他通道的输入、起始条件、传感器噪声与参考有效性。",
              "- 初始两通道温差不自动说明零偏或未平衡，设定值不当作环境实测。", "",
              "本报告不拟合参数、不选择最优功率、不执行设备操作。**不支持工程放行。**", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--before-seconds", type=float)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args(argv)
    try:
        report = analyze(args.data, args.before_seconds)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n" if args.format == "json" else markdown(report)
    except (ValueError, OSError, csv.Error, OverflowError) as error:
        print(f"记录诊断拒绝输入: {error}", file=sys.stderr)
        return 2
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
