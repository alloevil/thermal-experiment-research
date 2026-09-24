"""Reproduce the source and then compare predeclared time-holdout models."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import runpy
import shutil
import sys
import time
from pathlib import Path

for variable in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[variable] = '1'
os.environ['MPLBACKEND'] = 'Agg'

from thermal_model import (ROOT, INITIAL, LOWER, UPPER, SCALE, CAPACITY_J_K,
                           error_metrics, load_data, np, require, rollout)
from scipy.optimize import least_squares


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_source():
    manifest = json.loads((ROOT / 'upstream/manifest.json').read_text())
    for item in manifest['files']:
        require(digest(ROOT / 'upstream' / item['file']) == item['sha256'], f"Changed upstream {item['file']}")


def inspect_data(directory, data):
    import pandas as pd

    table = pd.read_csv(ROOT / 'upstream/data.txt', float_precision='round_trip')
    require(table.shape == (599, 7), 'Unexpected sample shape')
    np.testing.assert_array_equal(table.to_numpy(), data)
    changes = [index for index in range(len(data)) if index == 0 or not np.array_equal(data[index, 1:3], data[index - 1, 1:3])]
    require(changes == [0, 10, 100, 200, 300, 400, 500], 'Unexpected heater transitions')
    splits = {str(cut): {'train_rows': int(np.count_nonzero(data[:, 0] < cut)),
                          'validation_rows': int(np.count_nonzero(data[:, 0] >= cut))} for cut in [100, 300]}
    save(directory / 'data-inspection.json', {
        'rows': len(data), 'columns': [name.strip() for name in table.columns],
        'time_range_s': [float(data[0, 0]), float(data[-1, 0])],
        'dt_min_median_max_s': [float(np.diff(data[:, 0]).min()), float(np.median(np.diff(data[:, 0]))), float(np.diff(data[:, 0]).max())],
        'temperature_range_C': [[float(data[:, channel].min()), float(data[:, channel].max())] for channel in [3, 4]],
        'input_changes': [{'row': index, 'time_s': float(data[index, 0]), 'inputs_percent': data[index, 1:3].tolist()} for index in changes],
        'splits': splits, 'source_sha256': digest(ROOT / 'upstream/data.txt'),
        'source_label': 'Author-provided measured sample; not independently audited hardware',
    })


def native(directory, data):
    target = directory / 'native'
    target.mkdir()
    shutil.copyfile(ROOT / 'upstream/data.txt', target / 'data.txt')
    previous = Path.cwd()
    started = time.perf_counter()
    try:
        os.chdir(target)
        namespace = runpy.run_path(str(ROOT / 'upstream/mimo_fit.py'), run_name='__main__')
    finally:
        os.chdir(previous)
    elapsed = time.perf_counter() - started
    result = namespace['solution']
    output = namespace['Tp']
    checks = {}
    for name, parameters in [('initial', INITIAL), ('fitted', result.x)]:
        original = namespace['simulate'](parameters)
        local = rollout(data[:, 0], data[:, 1:3], data[0, 3:5], parameters)['temperature_C']
        difference = float(np.max(abs(original - local)))
        checks[name] = difference
        require(difference < .02, 'Adapted simulator diverges from original at identical parameters')
    import matplotlib.pyplot as plt

    plt.savefig(target / 'native-fit.png', dpi=150)
    plt.close('all')
    np.savez_compressed(target / 'prediction.npz', time=data[:, 0], measured_C=data[:, 3:5], predicted_C=output,
                        initial_prediction_C=namespace['Ti'], parameters=result.x)
    payload = {'status': 'COMPLETED', 'optimizer_success': bool(result.success), 'message': str(result.message),
               'parameters': result.x.tolist(), 'initial_parameters': INITIAL.tolist(),
               'initial_objective': float(namespace['objective'](INITIAL)), 'final_objective': float(result.fun),
               'all_data_metrics': error_metrics(output, data[:, 3:5]), 'scipy_nfev': int(result.nfev),
               'wall_seconds': elapsed, 'same_parameter_solver_max_difference_C': checks,
               'scope': 'Unmodified source script, full-data in-sample fit, not held-out validation. Agg backend only.'}
    save(target / 'result.json', payload)
    print('NATIVE_RESULT ' + json.dumps(payload), flush=True)
    return payload


def fit_training(times, inputs, measured, coupled, directory):
    require(np.all(measured != 0), 'Relative Celsius objective undefined at zero degrees')
    alpha2_identifiable = bool(np.any(inputs[:-1, 1] != 0))
    active = [0, 1, 2] if alpha2_identifiable else [0, 1]
    initial = INITIAL * SCALE
    evaluations = 0

    def parameters_from(active_values):
        values = initial.copy()
        values[active] = active_values
        return values / SCALE

    def residual(active_values):
        nonlocal evaluations
        parameters = parameters_from(active_values)
        predicted = rollout(times, inputs, measured[0], parameters, coupled)['temperature_C']
        relative = (predicted - measured) / measured
        evaluations += 1
        with (directory / 'fit-calls.jsonl').open('a') as output:
            output.write(json.dumps({'call': evaluations, 'parameters': parameters.tolist(),
                                     'train_relative_celsius_SSE': float(np.sum(relative**2))}) + '\n')
        return relative.ravel()

    started = time.perf_counter()
    solution = least_squares(residual, initial[active], bounds=((LOWER * SCALE)[active], (UPPER * SCALE)[active]),
                             method='trf', jac='3-point', max_nfev=100, ftol=1e-8, xtol=1e-8, gtol=1e-8)
    singular = np.linalg.svd(solution.jac, compute_uv=False)
    payload = {'optimizer_success': bool(solution.success), 'message': str(solution.message),
               'parameters': parameters_from(solution.x).tolist(), 'active_parameters': active,
               'alpha2_informed_by_training_input': alpha2_identifiable,
               'alpha2_if_uninformed': None if alpha2_identifiable else 'Fixed at author default 0.0075 W/percent; not an estimate.',
               'scipy_nfev': int(solution.nfev), 'actual_model_calls': evaluations,
               'wall_seconds': time.perf_counter() - started, 'active_bound_mask': solution.active_mask.tolist(),
               'jacobian_singular_values': singular.tolist(), 'jacobian_rank': int(np.linalg.matrix_rank(solution.jac)),
               'jacobian_condition_scaled_parameters': float(singular[0] / singular[-1]) if singular[-1] > 0 else None,
               'train_relative_celsius_SSE': float(np.sum(solution.fun**2))}
    save(directory / 'fit.json', payload)
    return payload


def heldout(directory, data):
    records = []
    for cut in [100, 300]:
        train_mask = data[:, 0] < cut
        for name, coupled in [('coupled', True), ('independent', False)]:
            target = directory / f'{name}-train-{cut}'
            target.mkdir()
            fit = fit_training(data[train_mask, 0], data[train_mask, 1:3], data[train_mask, 3:5], coupled, target)
            frozen = digest(target / 'fit.json')
            parameters = np.array(fit['parameters'])
            standard = rollout(data[:, 0], data[:, 1:3], data[0, 3:5], parameters, coupled)['temperature_C']
            strict = rollout(data[:, 0], data[:, 1:3], data[0, 3:5], parameters, coupled, tolerance_scale=.01)['temperature_C']
            error = float(np.max(abs(strict - standard)))
            require(error < .005, 'Time-integrator refinement changed predictions')
            energy = rollout(data[:, 0], data[:, 1:3], data[0, 3:5], parameters, coupled, ledger=True)
            stored = CAPACITY_J_K * (energy['temperature_C'] - data[0, 3:5]).sum(axis=1)
            ledger = energy['ledger_J']
            balance = float(np.max(abs(stored - ledger[:, 0] + ledger[:, 1] + ledger[:, 2])))
            exact_input = float(np.sum(np.diff(data[:, 0])[:, None] * data[:-1, 1:3] * parameters[1:]))
            require(balance < 1e-5 and abs(exact_input - ledger[-1, 0]) < 1e-5, 'Simulated heat accounting failed')
            np.savez_compressed(target / 'prediction.npz', time=data[:, 0], measured_C=data[:, 3:5], predicted_C=standard,
                                strict_prediction_C=strict, energy_temperature_C=energy['temperature_C'], ledger_J=ledger,
                                training_mask=train_mask, parameters=parameters)
            sensitivity = None
            if not fit['alpha2_informed_by_training_input']:
                alternatives = []
                for alpha2 in [LOWER[2], UPPER[2]]:
                    changed = parameters.copy()
                    changed[2] = alpha2
                    prediction = rollout(data[:, 0], data[:, 1:3], data[0, 3:5], changed, coupled)['temperature_C']
                    train_difference = float(np.max(abs(prediction[train_mask] - standard[train_mask])))
                    require(train_difference < 1e-7, 'Unexcited alpha2 affected training trajectory')
                    alternatives.append({'alpha2': float(alpha2), 'training_difference_C': train_difference,
                                         'validation_metrics': error_metrics(prediction[~train_mask], data[~train_mask, 3:5])})
                    np.savez_compressed(target / f'alpha2-{alpha2}.npz', prediction_C=prediction)
                sensitivity = alternatives
            require(frozen == digest(target / 'fit.json'), 'Fit changed after observing validation score')
            result = {'model': name, 'train_before_s': cut, 'training_rows': int(train_mask.sum()), 'validation_rows': int((~train_mask).sum()),
                      'fit': fit, 'fit_sha256': frozen, 'train_metrics': error_metrics(standard[train_mask], data[train_mask, 3:5]),
                      'validation_metrics': error_metrics(standard[~train_mask], data[~train_mask, 3:5]),
                      'refinement_max_difference_C': error, 'simulated_energy_max_balance_J': balance,
                      'exact_absorbed_J': exact_input, 'alpha2_sensitivity': sensitivity,
                      'initialization': 'Only row 0 measured temperatures; no validation-period resetting'}
            save(target / 'result.json', result)
            records.append(result)
            print(f"HOLDOUT {name} cutoff={cut} success={fit['optimizer_success']} params={fit['parameters']} "
                  f"train_RMSE={result['train_metrics']['rmse_C']:.4f}C validation_RMSE={result['validation_metrics']['rmse_C']:.4f}C", flush=True)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Output exists; preserve it and use a new path')
    require(not sys.flags.optimize, 'Run normally: upstream assertions must not be disabled')
    check_source()
    args.output.mkdir(parents=True)
    directory = args.output.resolve()
    data = load_data()
    require(data.shape == (599, 7), 'Pinned data size changed')
    sources = {name: digest(ROOT / name) for name in ['protocol.md', 'thermal_model.py', 'study.py', 'upstream/data.txt', 'upstream/mimo_fit.py', 'upstream/LICENSE']}
    save(directory / 'run-config.json', {'source_hashes': sources, 'split_times_s': [100, 300], 'model_order': ['coupled', 'independent'],
                                        'python': sys.version, 'platform': platform.platform(),
                                        'packages': {name: importlib.metadata.version(name) for name in ['numpy', 'scipy', 'pandas', 'matplotlib']}})
    inspect_data(directory, data)
    native_result = native(directory, data)
    records = heldout(directory, data)
    save(directory / 'summary.json', {'status': 'COMPLETED', 'native': native_result, 'comparisons': records,
                                     'scope': 'Author-supplied measured record; time holdout within one run, not independent hardware or active experiment validation.'})
    print('COMPLETED native replay and four predeclared holdout fits; see individual success/status fields', flush=True)


if __name__ == '__main__':
    main()
