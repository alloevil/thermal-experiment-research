"""Assess a two-heater record under explicitly accepted, fixed TCLab model assumptions."""

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import least_squares

from diagnose import analyze, read_record
from thermal_model import INITIAL, LOWER, UPPER, SCALE, ROOT, require, rollout


PARAMETERS = ['U', 'alpha1', 'alpha2']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def metrics(predicted, measured):
    residual = np.asarray(predicted) - np.asarray(measured)
    require(residual.ndim == 2 and residual.shape[1] == 2 and len(residual) > 0, 'Invalid scoring shape')
    require(np.isfinite(residual).all(), 'Non-finite residual')
    return {'rmse_C': float(np.sqrt(np.mean(residual**2))),
            'rmse_per_channel_C': np.sqrt(np.mean(residual**2, axis=0)).tolist(),
            'mae_C': float(np.mean(abs(residual))),
            'mae_per_channel_C': np.mean(abs(residual), axis=0).tolist(),
            'mean_residual_per_channel_C': np.mean(residual, axis=0).tolist()}


def fit_prefix(times, inputs, measured, directory):
    active = [0] + [channel + 1 for channel in range(2) if np.any(inputs[:-1, channel] != 0)]
    start = INITIAL * SCALE
    calls = 0

    def unpack(values):
        full = start.copy()
        full[active] = values
        return full / SCALE

    def residual(values):
        nonlocal calls
        parameters = unpack(values)
        prediction = rollout(times, inputs, measured[0], parameters)['temperature_C']
        difference = prediction - measured
        calls += 1
        with (directory / 'fit-calls.jsonl').open('a') as output:
            output.write(json.dumps({'call': calls, 'parameters': parameters.tolist(),
                                     'training_SSE_C2': float(np.sum(difference**2))}, allow_nan=False) + '\n')
        return difference.ravel()

    solution = least_squares(residual, start[active], bounds=((LOWER * SCALE)[active], (UPPER * SCALE)[active]),
                             method='trf', jac='3-point', max_nfev=100, ftol=1e-8, xtol=1e-8, gtol=1e-8)
    bounds = [0, 0, 0]
    for index, bound in zip(active, solution.active_mask):
        bounds[index] = int(bound)
    result = {'optimizer_success': bool(solution.success), 'message': str(solution.message),
              'parameters': unpack(solution.x).tolist(), 'parameter_order': PARAMETERS,
              'active_parameters': [PARAMETERS[index] for index in active],
              'fixed_unexcited_parameters': [name for index, name in enumerate(PARAMETERS) if index not in active],
              'active_bound_mask': bounds, 'scipy_nfev': int(solution.nfev), 'actual_model_calls': calls,
              'training_SSE_C2': float(np.sum(solution.fun**2)),
              'objective': 'Unweighted squared Celsius residuals; not the archived relative-Celsius objective.',
              'precision_status': 'not_established; single-start optimization is not parameter certainty'}
    save(directory / 'fit.json', result)
    require(result['optimizer_success'], 'Optimizer did not converge; inspect fit.json, do not use as a completed assessment')
    return result


def sensitivity_matrix(times, inputs, initial, parameters, fraction):
    parameters = np.asarray(parameters, float)
    require(parameters.shape == (3,) and np.all(parameters >= LOWER) and np.all(parameters <= UPPER), 'Parameters outside model bounds')
    span = UPPER - LOWER
    columns = []
    for index in range(3):
        below, above = parameters.copy(), parameters.copy()
        below[index] = max(LOWER[index], parameters[index] - fraction * span[index])
        above[index] = min(UPPER[index], parameters[index] + fraction * span[index])
        left = rollout(times, inputs, initial, below)['temperature_C'][1:]
        right = rollout(times, inputs, initial, above)['temperature_C'][1:]
        columns.append(((right - left) * span[index] / (above[index] - below[index])).ravel())
    return np.column_stack(columns)


def local_information(times, inputs, initial, parameters):
    coarse = sensitivity_matrix(times, inputs, initial, parameters, 1e-4)
    fine = sensitivity_matrix(times, inputs, initial, parameters, 5e-5)
    require(fine.shape[0] >= 3 and np.isfinite(fine).all() and np.isfinite(coarse).all(), 'Invalid sensitivity matrix')
    singular = np.linalg.svd(fine, full_matrices=False)
    values, directions = singular[1], singular[2]
    norms = np.linalg.norm(fine, axis=0)
    pairs = []
    for first in range(3):
        for second in range(first + 1, 3):
            denominator = norms[first] * norms[second]
            cosine = float(np.clip(np.dot(fine[:, first], fine[:, second]) / denominator, -1, 1)) if denominator else None
            pairs.append({'parameters': [PARAMETERS[first], PARAMETERS[second]], 'cosine': cosine})
    rank = int(np.linalg.matrix_rank(fine))
    norm = float(np.linalg.norm(fine))
    difference = float(np.linalg.norm(fine - coarse))
    return {'parameter_order': PARAMETERS, 'scaling': 'derivative with respect to (parameter - lower) / (upper - lower)',
            'rms_sensitivity_C_per_range': (norms / math.sqrt(len(fine))).tolist(),
            'singular_values': values.tolist(), 'numerical_rank': rank,
            'condition_number': float(values[0] / values[-1]) if rank == 3 else None,
            'weakest_scaled_direction': directions[-1].tolist(), 'column_cosines': pairs,
            'step_fractions': [1e-4, 5e-5], 'step_refinement_relative_difference': difference / norm if norm else None,
            'step_refinement_max_abs_difference': float(np.max(abs(fine - coarse))),
            'scope': 'Local, bounds-scaled, unwhitened sensitivities. No noise-calibrated confidence or global identifiability claim.'}, fine, coarse


def next_steps(excitation, fit, information):
    steps = []
    for channel in excitation['channels']:
        if channel['status'] == 'no_input_information':
            steps.append(f"{channel['parameter']}只保留默认假设：需要该路授权输入生效后的温度观测，或独立增益标定。")
        if channel['last_row_changed_without_followup']:
            steps.append(f"第{channel['heater']}路训练末行指令尚未在训练窗口内得到响应观测；先查找后续记录，不将末行本身当证据。")
    if any(fit['active_bound_mask']):
        steps.append('存在触及参数边界的拟合量；先审查边界依据、模型和测量，不据此宣称设备故障或直接放宽边界。')
    if information['numerical_rank'] < 3:
        steps.append('局部灵敏度存在数值退化；检查最弱参数组合及缺失激励，不把优化器成功当成三个参数均可估计。')
    steps.append('结合最弱参数方向、灵敏度列相似性、独立噪声/参考证据讨论补测；没有完整允许候选和成本，不给最优试验排名。')
    steps.append('执行前仍须确认模型/初态、输入单位与时序、允许幅值/变化率、温度限制、观测时长及其他通道控制。')
    return steps


def markdown(report):
    fit = report['fit']
    information = report['local_information']
    lines = ['# 热模型记录评估', '', '**同一记录的离线评估，不是硬件验证或补测收益证明。**', '',
             f"训练 {report['selection']['training_rows']} 行，后续检验 {report['selection']['validation_rows']} 行；仅首行实测温度用于初始化。", '',
             '## 参数能相信到什么程度', '', '|参数|值|来源|局部RMS灵敏度 °C/范围|边界标记|', '|---|---:|---|---:|---:|']
    for index, name in enumerate(PARAMETERS):
        origin = '默认假设，未估计' if name in fit['fixed_unexcited_parameters'] else '单初值拟合，精度未确立'
        lines.append(f"|{name}|{fit['parameters'][index]:.7g}|{origin}|{information['rms_sensitivity_C_per_range'][index]:.6g}|{fit['active_bound_mask'][index]}|")
    lines += ['', 'U单位为W/(m² K)，alpha单位为W/%；边界标记-1/0/1分别表示下界/未标记/上界。',
              f"局部数值秩：{information['numerical_rank']}/3；步长减半的相对矩阵差：{information['step_refinement_relative_difference']}。",
              f"最弱方向（U、alpha1、alpha2的范围缩放坐标）：{information['weakest_scaled_direction']}。",
              '它不是置信区间；边界上的方向不保证双向可行。灵敏度列余弦不是参数的统计相关系数。']
    for pair in information['column_cosines']:
        value = '未定义（存在零灵敏度列）' if pair['cosine'] is None else f"{pair['cosine']:.6f}"
        lines.append(f"- {' / '.join(pair['parameters'])}的灵敏度列余弦：{value}。绝对值接近1表示局部输出变化形状相似，不是不可辨识的单独证明。")
    lines += ['',
              '## 冻结参数后的预测', '',
              f"训练RMSE：{report['training_metrics']['rmse_C']:.6f}°C；后续RMSE：{report['validation_metrics']['rmse_C']:.6f}°C。",
              f"后续每通道平均残差（预测−测量）：{report['validation_metrics']['mean_residual_per_channel_C']}°C；不是零偏估计。",
              '没有预先给定的工程容差，不能把这些数字转为合格/不合格。后段实测没有参与拟合或灵敏度计算。']
    if report['unexcited_assumption_checks']:
        lines += ['', '未激励增益的外加假设敏感性（其他参数固定，不是联合置信区间）：']
        for item in report['unexcited_assumption_checks']:
            lines.append(f"- {item['parameter']}={item['value']:g}：训练最大预测差{item['training_max_difference_C']:.6g}°C，后续RMSE {item['validation_metrics']['rmse_C']:.6f}°C。")
    lines += ['', '## 下一步', ''] + ['- ' + step for step in report['next_steps']]
    lines += ['', '假设：固定23°C环境、作者双节点几何/热容量/辐射设定和参数范围；不是任意设备CSV的通用模型。',
              '**不支持工程放行；没有设备动作、最优补测排序或AI性能优势结论。**', '']
    return '\n'.join(lines)


def assess(path, before_seconds, output, accept_model_assumptions=False):
    require(accept_model_assumptions, 'Explicit --accept-model-assumptions is required; see ASSESSMENT.md')
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'Output exists; use a new directory')
    rows, source = read_record(path)
    excitation = analyze(path, before_seconds)
    require(source == excitation['source'], 'Input changed while reading')
    require(before_seconds is not None and math.isfinite(before_seconds) and before_seconds > 0, 'A finite positive cutoff is required')
    data = np.asarray(rows, float)
    training = data[:, 0] < before_seconds
    require(training.sum() >= 3 and (~training).sum() >= 1, 'Need at least three training rows and one subsequent measurement')
    prefix = data[training]
    output.mkdir(parents=True)
    started = time.perf_counter()
    try:
        save(output / 'status.json', {'status': 'RUNNING'})
        save(output / 'run-config.json', {'source': source, 'before_seconds_exclusive': before_seconds,
             'model': 'fixed APMonitor-style coupled TCLab; explicitly accepted assumptions in ASSESSMENT.md',
             'lower': LOWER.tolist(), 'upper': UPPER.tolist(), 'initial_parameters': INITIAL.tolist(),
             'source_hashes': {name: digest(ROOT / name) for name in ['assess.py', 'ASSESSMENT.md', 'thermal_model.py', 'diagnose.py']},
             'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__})
        fit = fit_prefix(prefix[:, 0], prefix[:, 1:3], prefix[:, 3:5], output)
        frozen = digest(output / 'fit.json')
        parameters = np.asarray(fit['parameters'])
        information, fine, coarse = local_information(prefix[:, 0], prefix[:, 1:3], prefix[0, 3:5], parameters)
        np.savez_compressed(output / 'local-sensitivity.npz', fine=fine, coarse=coarse, parameters=parameters,
                            training_time=prefix[1:, 0])
        prediction = rollout(data[:, 0], data[:, 1:3], data[0, 3:5], parameters)['temperature_C']
        alternatives = []
        for name in fit['fixed_unexcited_parameters']:
            index = PARAMETERS.index(name)
            for value in [LOWER[index], UPPER[index]]:
                changed = parameters.copy()
                changed[index] = value
                predicted = rollout(data[:, 0], data[:, 1:3], data[0, 3:5], changed)['temperature_C']
                difference = float(np.max(abs(predicted[training] - prediction[training])))
                require(difference < 1e-7, 'Unexcited parameter changed the training trajectory')
                alternatives.append({'parameter': name, 'value': float(value), 'training_max_difference_C': difference,
                    'validation_max_prediction_difference_C': float(np.max(abs(predicted[~training] - prediction[~training]))),
                    'validation_metrics': metrics(predicted[~training], data[~training, 3:5])})
        require(frozen == digest(output / 'fit.json'), 'Frozen fit changed during evaluation')
        require(digest(path) == source['sha256'], 'Input changed during evaluation')
        report = {'schema': 'tclab-record-assessment/1', 'source': source,
                  'selection': {'before_seconds_exclusive': before_seconds, 'training_rows': int(training.sum()),
                                'validation_rows': int((~training).sum()), 'last_training_time_s': float(prefix[-1, 0])},
                  'excitation': excitation, 'fit': fit, 'fit_sha256': frozen, 'local_information': information,
                  'training_metrics': metrics(prediction[training], data[training, 3:5]),
                  'validation_metrics': metrics(prediction[~training], data[~training, 3:5]),
                  'unexcited_assumption_checks': alternatives, 'next_steps': next_steps(excitation, fit, information),
                  'precision_status': 'not_established', 'engineering_release': 'not_supported', 'hardware_action': 'none',
                  'scope': 'Single-record temporal holdout under fixed model assumptions, not prospective experiment validation.'}
        with (output / 'prediction.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['time_s', 'training', 'measured_T1_C', 'measured_T2_C', 'predicted_T1_C', 'predicted_T2_C'])
            for index, row in enumerate(data):
                writer.writerow([row[0], int(training[index]), *row[3:5], *prediction[index]])
        save(output / 'report.json', report)
        (output / 'report.md').write_text(markdown(report))
        save(output / 'status.json', {'status': 'COMPLETED', 'wall_seconds': time.perf_counter() - started,
                                     'engineering_release': 'not_supported'})
        return report
    except Exception as error:
        save(output / 'status.json', {'status': 'FAILED', 'error_type': type(error).__name__, 'message': str(error)})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--before-seconds', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--accept-model-assumptions', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = assess(args.data, args.before_seconds, args.output, args.accept_model_assumptions)
    except (ValueError, OSError, RuntimeError, ArithmeticError, np.linalg.LinAlgError) as error:
        print(f'记录评估未完成: {error}', file=sys.stderr)
        return 2
    print(markdown(report))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
