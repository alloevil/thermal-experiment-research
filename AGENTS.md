# Thermal Experiment Research

## Scope and language
- Respond in Chinese unless the user requests otherwise. This is the full research repository, not only the latest prototype.
- Read intent.md and PRODUCT_DIRECTION.md before changing the direction. README.md and README.zh-CN.md are the maintained public entry points; historical stage documentation is preserved evidence.
- No real equipment, customer data, metrological certification, or industrial safety has been validated. Never convert a successful solver, small residual, or clean hash check into an engineering release claim.

## Archive boundaries
- Do not silently alter stage results, sources, logs, pinned manifests, or failed experiments to make tests pass.
- Eight stage manifests are pinned by workbench.py. New experiments belong in new directories with explicit protocols, not over the recorded results.
- docs/archive-import.json records the original imported tree; docs/archive-replacements.json and docs/reference-publication.json disclose the public-edition source notices and omitted external binaries. Do not restore token-bearing HTML or third-party full text without a separate rights review.
- Upstream source snapshots and papers retain their own rights. Do not add a blanket license, publish, push, or upload externally without explicit authorization.
- The owner authorized this first public release after processing external references. Future new externally sourced material still needs an explicit review; public-edition pins in workbench.py intentionally differ for radiation/calibration source notices, not scientific results.

## Commands
- `python workbench.py check` verifies pinned file integrity only; it does not rerun experiments.
- `python scripts/check.py --quick` uses the standard library for import-integrity and entrypoint checks.
- `python scripts/check.py` additionally runs the existing evidence-report, prototype/workflow, and array-verification tests; install requirements-thermal.lock explicitly first.
- `python next_experiment/demo_workflow.py --output /tmp/new-thermal-demo` stops at review. `--approve-simulation` opts into a synthetic observation only.
- `python tools/replay_thermal.py --python /path/to/python --output /new/directory` explicitly runs an isolated copy of the frozen thermal experiment.
- Keep new validation logs and screenshots under ignored output/, never redirect into old stage logs.
- Avoid importing unrelated test modules into one interpreter: stage modules share historical names such as core and model; run each suite in its own process.

## Change discipline
- No new dependencies, abstractions, benchmarks, retries, or platforms without a concrete user-facing task.
- Reproduce bugs before fixing them; test successful, ambiguous, rejected, and failure paths.
- Preserve the finite-grid, noise, independence, budget, and reference assumptions in recommendations.
- For UI/README work, use deterministic SVG for diagrams and Markdown for copy; preview at 900px and 360px. Don't invent results or adoption.
