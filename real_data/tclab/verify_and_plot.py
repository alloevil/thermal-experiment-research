"""Recompute reported scores, split membership and source-model agreement."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path

os.environ['MPLBACKEND'] = 'Agg'
for variable in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[variable] = '1'

import numpy as np
from thermal_model import ROOT, CAPACITY_J_K, fluxes, load_data, require, rollout


def load(path):
    return json.loads(path.read_text())


def close(actual, expected, name, atol=1e-9):
    require(np.allclose(actual, expected, rtol=1e-9, atol=atol), f'Incorrect {name}: {actual} vs {expected}')


def scores(prediction, measured, expected):
    residual = prediction - measured
    close(np.sqrt(np.mean(residual**2)), expected['rmse_C'], 'RMSE')
    close(np.sqrt(np.mean(residual**2, axis=0)), expected['rmse_per_channel_C'], 'channel RMSE')
    close(np.mean(abs(residual)), expected['mae_C'], 'MAE')
    close(np.mean(abs(residual), axis=0), expected['mae_per_channel_C'], 'channel MAE')
    close(np.sum((residual / measured)**2), expected['relative_celsius_SSE'], 'relative Celsius objective')


def verify(directory):
    data = load_data()
    config = load(directory / 'run-config.json')
    for name, checksum in config['source_hashes'].items():
        require(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == checksum, f'Frozen source changed: {name}')
    for item in load(ROOT / 'upstream/manifest.json')['files']:
        require(hashlib.sha256((ROOT / 'upstream' / item['file']).read_bytes()).hexdigest() == item['sha256'], 'Upstream changed')
    require(data.shape == (599, 7), 'Wrong data shape')
    summary = load(directory / 'summary.json')
    native = load(directory / 'native/result.json')
    require(native == summary['native'], 'Native summary differs')
    require(hashlib.sha256((directory / 'native/data.txt').read_bytes()).hexdigest() == config['source_hashes']['upstream/data.txt'], 'Native script did not receive original data')
    with np.load(directory / 'native/prediction.npz', allow_pickle=False) as arrays:
        np.testing.assert_array_equal(arrays['time'], data[:, 0])
        np.testing.assert_array_equal(arrays['measured_C'], data[:, 3:5])
        scores(arrays['predicted_C'], data[:, 3:5], native['all_data_metrics'])
        close(np.sum(((arrays['predicted_C'] - data[:, 3:5]) / data[:, 3:5])**2), native['final_objective'], 'native objective')
    source_tree = ast.parse((ROOT / 'upstream/mimo_fit.py').read_text())
    heat_function = next(node for node in source_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'heat')
    scope = {}
    exec(compile(ast.Module(body=[heat_function], type_ignores=[]), 'original-heat', 'exec'), scope)
    generator = np.random.default_rng(20261003)
    max_rate_difference = 0.
    for _ in range(20):
        state = generator.uniform(18, 60, 2)
        inputs = generator.uniform(0, 100, 2)
        parameters = generator.uniform([2, .005, .002], [20, .02, .015])
        native_rate = np.array(scope['heat'](state, 0, inputs[0], inputs[1], parameters))
        local_rate = fluxes(state, inputs, parameters)[0] / CAPACITY_J_K
        difference = float(np.max(abs(native_rate - local_rate)))
        max_rate_difference = max(max_rate_difference, difference)
        require(difference < 1e-12, 'Adapted energy equation differs from author equation')
    fit_tree = ast.parse((ROOT / 'study.py').read_text())
    fit_function = next(node for node in fit_tree.body if isinstance(node, ast.FunctionDef) and node.name == 'fit_training')
    require([arg.arg for arg in fit_function.args.args] == ['times', 'inputs', 'measured', 'coupled', 'directory'], 'Fitter interface changed')
    numerical_checks = []
    for record in summary['comparisons']:
        cut, model_name = record['train_before_s'], record['model']
        folder = directory / f'{model_name}-train-{cut}'
        mask = data[:, 0] < cut
        require(mask.sum() == (100 if cut == 100 else 300), 'Unexpected split')
        fit = load(folder / 'fit.json')
        require(fit == record['fit'], 'Fit changed in summary')
        require(hashlib.sha256((folder / 'fit.json').read_bytes()).hexdigest() == record['fit_sha256'], 'Fit changed after validation')
        require(fit['scipy_nfev'] <= 100, 'Budget exceeded')
        call_records = [json.loads(line) for line in (folder / 'fit-calls.jsonl').read_text().splitlines()]
        require([item['call'] for item in call_records] == list(range(1, fit['actual_model_calls'] + 1)), 'Missing fit evaluations')
        require(fit['active_parameters'] == ([0, 1] if cut == 100 else [0, 1, 2]), 'Invalid active parameter set')
        if cut == 100:
            require(not fit['alpha2_informed_by_training_input'] and fit['parameters'][2] == .0075, 'Unexcited parameter called fitted')
        with np.load(folder / 'prediction.npz', allow_pickle=False) as arrays:
            require(arrays['predicted_C'].shape == arrays['measured_C'].shape == (599, 2), 'Wrong output shape')
            np.testing.assert_array_equal(arrays['time'], data[:, 0])
            np.testing.assert_array_equal(arrays['training_mask'], mask)
            np.testing.assert_array_equal(arrays['measured_C'], data[:, 3:5])
            prediction = arrays['predicted_C']
            scores(prediction[mask], data[mask, 3:5], record['train_metrics'])
            scores(prediction[~mask], data[~mask, 3:5], record['validation_metrics'])
            close(record['train_metrics']['relative_celsius_SSE'], fit['train_relative_celsius_SSE'], 'frozen training objective')
            require(np.max(abs(arrays['strict_prediction_C'] - prediction)) < .005, 'Time refinement failure')
            stored = CAPACITY_J_K * (arrays['energy_temperature_C'] - data[0, 3:5]).sum(axis=1)
            ledger = arrays['ledger_J']
            require(np.max(abs(stored - ledger[:, 0] + ledger[:, 1] + ledger[:, 2])) < 1e-5, 'Integrated model energy failure')
            expected_absorbed = np.sum(np.diff(data[:, 0])[:, None] * data[:-1, 1:3] * np.array(fit['parameters'])[1:])
            close(ledger[-1, 0], expected_absorbed, 'applied-input energy', atol=1e-5)
            prefix = rollout(data[mask, 0], data[mask, 1:3], data[0, 3:5], fit['parameters'], coupled=model_name == 'coupled')['temperature_C']
            close(prefix, prediction[mask], 'prefix must not depend on later data', atol=1e-8)
            tail_start = int(mask.sum()) - 1
            continuation = rollout(data[tail_start:, 0], data[tail_start:, 1:3], prediction[tail_start], fit['parameters'], coupled=model_name == 'coupled')['temperature_C']
            close(continuation, prediction[tail_start:], 'holdout must continue simulated state', atol=1e-8)
            if cut == 100:
                for alternative in record['alpha2_sensitivity']:
                    with np.load(folder / f"alpha2-{alternative['alpha2']}.npz") as saved:
                        np.testing.assert_allclose(saved['prediction_C'][mask], prediction[mask], rtol=0, atol=1e-7)
                        scores(saved['prediction_C'][~mask], data[~mask, 3:5], alternative['validation_metrics'])
            numerical_checks.append({'model': model_name, 'cutoff_s': cut, 'validation_rows': int((~mask).sum()),
                                     'prefix_and_continuation_verified': True})
    result = {'status': 'PASS', 'upstream_equation_random_checks': 20, 'maximum_rate_difference_C_per_s': max_rate_difference,
              'frozen_fits_verified': 4, 'checks': numerical_checks,
              'scope': 'Source/data/rollout verification only; no ground-truth fault, new hardware experiment or causal performance claim.'}
    (directory / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS original data hashes/units and native in-sample scores')
    print('PASS 20 author-equation checks and frozen 100s/300s training splits')
    print('PASS four holdout scores, call budgets, prefix isolation and uninterrupted validation rollout')
    print('PASS unexcited alpha2 invariance, time refinement and simulated energy ledger')
    return summary


def plot(directory, summary):
    import matplotlib.pyplot as plt

    data = load_data()
    figure, axes = plt.subplots(3, 2, figsize=(12, 9), constrained_layout=True)
    for column, cutoff in enumerate([100, 300]):
        for sensor in range(2):
            axis = axes[sensor, column]
            axis.plot(data[:, 0], data[:, 3 + sensor], 'k-', linewidth=1.2, label='Author measured sample')
            for name, color in [('coupled', '#24799c'), ('independent', '#b65d35')]:
                with np.load(directory / f'{name}-train-{cutoff}/prediction.npz') as arrays:
                    axis.plot(data[:, 0], arrays['predicted_C'][:, sensor], color=color, label=name)
            axis.axvspan(cutoff, data[-1, 0], color='#778b99', alpha=.12, label='Held-out continuation' if sensor == 0 else None)
            axis.axvline(cutoff, color='#55616b', linestyle='--', linewidth=1)
            axis.set(ylabel=f'T{sensor + 1} (°C)', xlabel='Time (s)', title=f'Train before {cutoff}s — sensor {sensor + 1}')
            axis.grid(alpha=.2)
            if sensor == 0:
                axis.legend(fontsize=8)
        axis = axes[2, column]
        for heater, color in [(1, '#24799c'), (2, '#b65d35')]:
            axis.step(data[:, 0], data[:, heater], where='post', color=color, label=f'Heater {heater}')
        axis.axvline(cutoff, color='#55616b', linestyle='--', linewidth=1)
        axis.set(xlabel='Time (s)', ylabel='Heater command (%)', title='Recorded input; no counterfactual experiment')
        axis.legend(fontsize=8)
        axis.grid(alpha=.2)
    figure.suptitle('TCLab: full-data fit is not held-out prediction — Apache-2.0 APMonitor author sample', fontsize=12)
    figure.savefig(directory / 'holdout-comparison.png', dpi=150)
    plt.close(figure)
    print('PASS holdout-comparison.png rendered')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', required=True, type=Path)
    args = parser.parse_args()
    summary = verify(args.results)
    plot(args.results, summary)


if __name__ == '__main__':
    main()
