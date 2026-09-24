# 第四阶段复现与审计

在本目录运行。复用 `../feasibility/.venv`，不修改前三阶段源码、结果或依赖。

## 已固定环境

```sh
uv pip check --python ../feasibility/.venv/bin/python
```

缺少环境时按 `../feasibility/RUNBOOK.md` 创建，使用已锁定的39个包。本阶段使用SciPy经典最小二乘和SLSQP，不使用LLM或神经网络。

## 模型验证

```sh
set -o pipefail
../feasibility/.venv/bin/python -u check_effective.py 2>&1 | tee logs/model-checks-rerun.log
```

检查标称等价、物理比例到有效比值的温度等价、归一化热量与Jacobian。热容量固定仅为数学坐标，不代表知道真实热容量；有效辐射乘子不是物理发射率。

## 主实验

```sh
timeout 900s ../feasibility/.venv/bin/python -u run_experiment.py 2>&1 | tee logs/experiment-rerun.log
```

读取预注册的8个对象，生成观测，做16次独立拟合和对应重优化；标称重优化只做一次。观测噪声种子、参数盒、初始值、预算和所有脚本/依赖哈希在首次运行前保存于 `results/config.json`。

运行完成后拒绝重复优化，只提示执行验证。中断时已完成拟合/控制/对象阶段可以复用；若某阶段只有调用日志而没有完成结果，将拒绝静默重新开始。应先将对应未完成阶段记录归档，再明确重启该阶段。它不是优化器内部状态的精确恢复。

若希望完全重跑，将整个 `results/` 和本轮日志移入新的归档目录，先重新执行模型验证，再执行主实验。不要只删除表现不佳的对象后重算。

## 结果验收与绘图

```sh
../feasibility/.venv/bin/python -u verify_results.py 2>&1 | tee logs/verification-rerun.log
../feasibility/.venv/bin/python plot_results.py
```

验证程序检查配置哈希、观测生成、拟合接口与冻结结果、调用预算、预测误差、真实能量收支、输入与温度限制。它会重新计算全部16个最终拟合预测并记录警告，核对保存残差；另外重新生成对象0和7的干净标定观测。

验证不会重新拟合或选择新参数，不用留出数据改进拟合。数值PASS不等于所有策略必须满足工艺条件；失败候选也保留。

## 关键文件

- `effective.py`：四个有效比值的归一化模型、传感器投影。
- `fit_and_control.py`：拟合函数仅接受时间、带噪温度和输出目录，不接收隐藏物理参数或留出结果；重优化使用统一约束与预算。
- `run_experiment.py`：生成端和评价端持有真实参数，拟合冻结后才用于评分。
- `results/object-N/observations.npz`：同一物理对象的干净观测和两个带噪版本；每次拟合仅使用其中一个带噪版本的144个观测。
- `results/object-N/noise-R/fit.json`：冻结有效比值、残差、边界状态和局部Jacobian诊断。
- `fit-calls.jsonl` / `control-calls.jsonl`：真实求解调用，有限差分求Jacobian的调用也计入。
- `heldout-predictions.npz`：未参与拟合的固定输入下，96单元真实/标称/校准温度场。
- `calibrated-physical.npz`：真实物理模型对校准重优化指令的反馈，记录绝对温度、真实热量和吸收功率。
- `results/verification.json`：全量复核结果、最终拟合预测重放及警告记录。

## 限制

同结构、已知初温、无传感器偏置、理想位置、独立高斯噪声，是乐观的合成条件。额外校准观测和拟合成本不可忽略；两噪声实现不等于16台独立设备。不得将有效参数误当真实物性或将本实验称为实物、工业、安全验证。

若重新生成产物，需重新记录哈希清单；报告中的实测耗时不会自动更新。
