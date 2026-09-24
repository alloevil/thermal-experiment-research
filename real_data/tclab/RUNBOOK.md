# Run the author-supplied TCLab case

## Scope

This is a dedicated two-heater / two-temperature adapter for APMonitor's measured sample. It is not input for the previous three-zone synthetic `next_experiment` model. The data headers are seconds, heater percent and degrees Celsius; the radiation equation converts Celsius to Kelvin internally.

The original data/script are included under the supplied upstream Apache-2.0 license. Source URLs and hashes are in `upstream/manifest.json`; attribution and changes are documented in `ATTRIBUTION.md`. Do not download or operate hardware to execute this offline example.

## Diagnose input information without fitting

The read-only diagnostic accepts the explicit five- or seven-column CSV schema described in [DIAGNOSIS.md](DIAGNOSIS.md). It uses only the Python standard library and does not change the fixed-data fitting study:

```sh
python -B real_data/tclab/diagnose.py \
  --data real_data/tclab/upstream/data.txt --before-seconds 100
```

It reports missing heater-gain excitation and conditional follow-up requirements, not full identifiability or equipment approval. The terminal input has no subsequent observation and is excluded. See [recorded diagnostic results](DIAGNOSIS_RESULTS.md) for the 100/101/300-second prefixes.

## Assess a prefix and its subsequent prediction

With an existing NumPy/SciPy environment, `assess.py` fits only the selected prefix, checks local parameter sensitivity, freezes the fit and evaluates subsequent temperatures without resetting state. See [ASSESSMENT.md](ASSESSMENT.md) for the required fixed-model assumptions and the new unweighted Celsius objective, which is deliberately separate from the archived author-relative objective.

```sh
.venv-tclab/bin/python -B real_data/tclab/assess.py \
  --data real_data/tclab/upstream/data.txt --before-seconds 300 \
  --accept-model-assumptions --output /tmp/tclab-record-assessment
```

Use a new directory. [Measured assessment results](ASSESSMENT_RESULTS.md) retain the missing-excitation and parameter-bound warnings; they do not establish prospective experiment benefit, statistical confidence or industrial suitability. The installation below supports both this assessment and the larger original reproduction; the assessment itself needs no Pandas or plotting package.

## Install the isolated analysis environment

From the repository root:

```sh
python3.12 -m venv --without-pip .venv-tclab
uv pip install --python .venv-tclab/bin/python --require-hashes --only-binary :all: \
  -r real_data/tclab/requirements.lock
uv pip check --python .venv-tclab/bin/python
```

The author script and spreadsheet/plotting inspection need Pandas and Matplotlib in addition to NumPy/SciPy. This environment is separate from the existing two-package model environment; do not replace the old locks. Tested on the current Linux/CPython 3.12 host only.

## Recompute into a new directory

```sh
set -o pipefail
.venv-tclab/bin/python -B real_data/tclab/study.py \
  --output /tmp/my-new-tclab-study
.venv-tclab/bin/python -B real_data/tclab/verify_and_plot.py \
  --results /tmp/my-new-tclab-study
```

The output directory must not exist. `study.py` retains the fixed data, runs the unmodified author's full-data optimizer, freezes four new early-data fits, and only then evaluates each respective holdout. It writes new output, not archived historical evidence. The verifier recomputes metrics, exact split membership, power/energy arithmetic and independent prefix/continuation rollouts, and produces a new plot.

Default data path is the included fixed-commit `upstream/data.txt`; this first study intentionally has no generic CSV importer or arbitrary parameter-fitting configuration. To test another dataset, first define its headers, units, sample/actuation timing and evaluation protocol rather than relabeling this case.

## Verify the recorded result

```sh
.venv-tclab/bin/python -B -m unittest discover \
  -s real_data/tclab -p 'test_*.py' -v
.venv-tclab/bin/python -B real_data/tclab/verify_and_plot.py \
  --results real_data/tclab/results/locked-run
```

The second command regenerates that stage's verification JSON/figure, so use a copied result directory if preserving byte-identical verification artifacts matters. Tests only mutate temporary copies. Core tests also run with the existing NumPy/SciPy environment; plotting and native reproduction require the four-package analysis specification.

## Outputs and failure handling

- `run-config.json`: exact source/protocol hashes, split times and executed package versions.
- `data-inspection.json`: pandas/NumPy consistency, observed input changes, actual sample intervals and units.
- `native/`: original program result, copied original input, prediction and figure; full-data in-sample evidence only.
- `coupled-train-100/`, `independent-train-100/`, `coupled-train-300/`, `independent-train-300/`: frozen fit, every fit-call score, full forward prediction, time refinement, energy balance and holdout metrics.
- Early-fit `alpha2-*.npz`: endpoint sensitivity using the author's bounds, not extra optimized methods. The second heater gain was not estimated from the early unexcited input.
- `verification.json`, `holdout-comparison.png`: independent recomputation and visualization.

Failed fits are recorded with their solver status. This run does not resume optimizer internals or silently retry with new bounds/initial guesses. If interrupted, preserve the partial result directory and use a new one for a complete rerun.

All error bars and predictions are numerical outputs from a limited model. There are no measured heat-flow data, fault labels, certified sensor offsets or experimentally observed alternatives for a trial that never happened. Do not interpret holdout success as active experimental-design benefit or production approval.
