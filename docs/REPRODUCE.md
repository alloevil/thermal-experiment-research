# Reproduce from the repository root

## Environment levels

| Level | Dependencies | What it can do |
|---|---|---|
| Read and inspect | Python standard library | `workbench.py list/check`, `scripts/check.py --quick` |
| Report only | `requirements-report.lock` (NumPy) | `workbench.py report` recomputes saved-array evidence summaries |
| Prototype / thermal example | `requirements-thermal.lock` (NumPy + SciPy) | next-experiment CLI, review workflow, full selected tests, isolated thermal replay |
| Original broader studies | `feasibility/requirements.lock` (39 packages) | Includes the original BoTorch / py-pde environment; not needed to try the latest prototype |

The main local verification during repository preparation uses a new virtual environment, not a symlink to the old workspace. Installation remains explicit; do not copy prebuilt virtual environments into Git.

## Main path

```sh
python3.12 -m venv --without-pip .venv
uv pip install --python .venv/bin/python --require-hashes --only-binary :all: \
  -r requirements-thermal.lock
.venv/bin/python scripts/check.py
.venv/bin/python next_experiment/demo_workflow.py \
  --output /tmp/new-thermal-workflow --approve-simulation
```

These POSIX commands are tested on Linux/CPython 3.12. The workflow simulates observations only when explicitly requested; it does not contact devices or model APIs.

## What the main check does

1. Verify all imported research files against docs/archive-import.json, accepting only explicitly documented replacements in docs/archive-replacements.json.
2. Run the eight pinned stage snapshot checks (integrity, not scientific validation).
3. Run standard-library entrypoint tests, evidence-report tests, next-experiment/review-workflow tests, and the saved-array thermal-replay verifier tests in separate processes.

It does **not** automatically refit every dataset, regenerate historical plots, run all original upstream test suites, execute downloaded source snippets, or prove physical accuracy. Some historical scripts share module names; separate processes avoid accidental test import collisions.

CI runs this same command with the NumPy/SciPy lock. No public Actions result exists until the owner actually publishes/runs the workflow; a locally passing check is not a fabricated GitHub badge.

## A new scientific run

```sh
python tools/replay_thermal.py --python .venv/bin/python \
  --output /tmp/new-thermal-science
```

This copies the frozen thermal example into a fresh directory, solves the ODE checks, runs the constrained optimizer once, then independently recomputes its saved fields/energy metrics. It refuses an existing output directory. It still uses the same synthetic physics and is not an independent hardware validation.

## Full historical reproduction

Study-specific instructions are in each RESULTS.md, RUNBOOK.md, GUIDE.md or WORKFLOW.md. Older logs record old host paths and are deliberately not rewritten. Use relative commands from this root or adapt a historical command explicitly; do not assume every recorded command is portable verbatim.

The entire results and source archive is kept. A full numerical rerun may create different wall-clock logs or derived files. Never redirect into frozen evidence or blindly refresh hash pins to make an integrity failure disappear; use a new result directory and describe the difference.

## License and data boundary

Reproduction instructions are not a grant to redistribute third-party papers, snapshots or code. Review THIRD_PARTY.md and docs/PUBLICATION.md before public release. The root license for original work remains undecided.
