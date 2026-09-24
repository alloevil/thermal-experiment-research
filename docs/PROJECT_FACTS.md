# Project facts / 项目事实索引

This page summarizes current code and recorded studies. It is not a product requirements document, a safety certificate or a claim of external adoption. 中文：本页概括现有代码与实验，不把规划功能写成已实现能力。

## What is Thermal Experiment Research?

Thermal Experiment Research is a complete Python research archive for thermal modeling, parameter calibration and model discrimination through next-experiment selection. The current prototype compares convection changes with sensor offset, recommends an allowed experiment, records a research review, and updates candidate support after receiving observations.

这是一个完整 Python 热工程研究仓库。当前原型比较散热变化与测温零偏，推荐允许试验，记录研究审核，再用新观测更新候选支持度。它不是任意设备诊断系统，也不接真实硬件。

## Current capabilities and their evidence

| Fact / 事实 | Source / 依据 |
|---|---|
| The thermal example models conduction, convection losses and nonlinear radiative losses using synthetic/teaching parameters. | [Model and parameter assumptions](../radiation/protocol.md), [implementation](../radiation/model.py) |
| Candidate comparison retains a finite grid over mechanisms and nuisance parameters; probabilities are relative to those candidate grids. | [Prototype protocol](../next_experiment/protocol.md), [implementation](../next_experiment/core.py) |
| The prototype selects only enabled, budget-feasible experiments passing the declared finite-grid temperature screen. | [Input contract and limits](../next_experiment/GUIDE.md) |
| The plan/review/observe workflow records local research approval; reviewer labels are not identity authentication. | [Workflow](../next_experiment/WORKFLOW.md), [recorded execution](../next_experiment/WORKFLOW_RESULTS.md) |
| Core prototype and thermal replay need NumPy/SciPy on CPU, not an LLM endpoint, GPU or equipment connection. Other historical experiments have their own dependencies. | [Environment levels](REPRODUCE.md), [thermal dependency lock](../requirements-thermal.lock) |
| All engineering-release fields remain unsupported. | [Scope in the prototype guide](../next_experiment/GUIDE.md), [evidence report](../evidence_report/contract.md) |

## Results that may be quoted—with their conditions

- **Model-selection comparison:** information gain and the simple mean-separation heuristic both made 13 decisions and retained 3 ambiguous outcomes across 16 synthetic cases; fixed cooldown had a slightly lower mean Brier score. This does **not** establish a new-algorithm advantage. [Protocol, table and limitations](../next_experiment/RESULTS.md).
- **Residual-warning blind spots:** 5 combined-warning misses persisted in the small-bias study after the documented refinement checks. That is a count in a fixed design, not a population failure rate. [Bias-boundary study](../bias_boundary/RESULTS.md).
- **Reference error:** a +0.35 K synthetic reference bias left 4 corrected cases inadequate and unflagged in the recorded paired experiment. This is not a specification for any actual thermometer. [Reference-correction study](../reference_correction/RESULTS.md).

Quoted results must name their study, input/noise assumptions and comparator. Different stages, noise replicates and reused observations must not be added together as independent samples. 中文：引用时必须同时带上研究条件，不能把这些数值当成工业故障率或普适性能指标。

## Not established

- No real semiconductor chamber, material recipe, production line or independent hardware validation.
- No verified company partnership, user adoption, citation count or commercial benefit.
- No continuous-time safety certificate, globally unique parameter identification, or calibrated real-world confidence intervals.
- No general CSV-to-physics importer, LLM planner, reinforcement-learning policy or general-purpose optimization platform.
- No confirmed project-specific paper, DOI, tagged software release or blanket repository license. The public source repository is https://github.com/alloevil/thermal-experiment-research .

The project investigates AI4Engineering questions; that label is a research direction, not evidence that an AI component currently beats classical tools. [Product direction](../PRODUCT_DIRECTION.md).

## How to cite a specific claim

Use the study report and its protocol, then record the actual commit/release identifier and source URL once the repository is published. Keep a downloaded paper's authors separate from the authors of this repository. The current naming and attribution decisions are in [CITATION.md](../CITATION.md); do not invent a DOI, author list or publication date from local execution logs.
