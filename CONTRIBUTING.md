# Contributing to the research record

Start with PRODUCT_DIRECTION.md and STATUS.md. Useful contributions improve a concrete modeling, experiment-selection or reproduction task—not the number of frameworks or dashboards.

1. State the hypothesis, input assumptions, allowed experiments and failure criterion before collecting new evaluation results.
2. Retain negative outcomes and distinguish development examples from held-out evaluation.
3. Keep archived protocols, arrays, logs and manifests unchanged. New studies/results belong in new directories; disclose corrections rather than silently replacing evidence.
4. Never submit customer logs, credentials, private geometry or data without authorization. Synthetic approval records are not hardware permission.
5. Run `python scripts/check.py` in the documented NumPy/SciPy environment. It does not rerun the entire research program; describe additional numerical tests relevant to your change.
6. Explain license/provenance for new data, figures and upstream code. Root licensing is not yet selected; do not assume all references are freely redistributable.

Report bugs with the command, input/example, expected behavior and actual error. Include the environment but remove secrets. Do not report a solver success flag or a small residual as an engineering safety guarantee.
