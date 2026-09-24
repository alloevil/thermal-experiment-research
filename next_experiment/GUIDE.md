# 下一次试验助手：第一版本地原型

**输入已有测试记录 → 比较两个解释 → 推荐允许的下一次试验 → 输入新观测 → 更新判断。**

当前专用于已有教学热模型：散热系数变化（convection）与测温零偏（offset）。不支持任意CAD/CSV自动理解，不执行真实设备命令，不给安全放行。它使用有限参数网格的贝叶斯模型辨别，不调用LLM，也未证明新算法优于经典方法。

## 一条命令跑完整演示

在项目根`research/thermal-ai4engineering`运行：

```sh
feasibility/.venv/bin/python next_experiment/cli.py demo --output /tmp/next-test-demo
```

输出目录必须不存在；不要指向旧阶段归档。没有现成环境时，按根QUICKSTART.md创建NumPy/SciPy双包环境，并用`.venv-thermal/bin/python`替换解释器。CLI不需要Matplotlib；`plot_demo.py`是可选绘图脚本，只在已有绘图环境中使用。

演示会保存：

- `case.json`：模型先验、试验集合、预算、温度筛选与测量噪声。
- `observations.json`：已有测试数据。
- `recommendation.md`：建议卡，包含功率步骤、测量位置/时间、两解释预测区间、成本与前提。
- `recommendation.json`：同一建议的机器可读输出，含所有可用候选的评分。
- `measurement.json`：仅在演示中模拟产生的新增观测；实际使用应替换为实测数据。
- `updated-observations.json` / `updated-posterior.json`：追加后的数据和候选支持度。
- `indistinguishable.json` / `unsupported.json`：等价模型无法区分及候选集合无法解释观测的两个出口。
- `simulation-truth.json`：演示评分用真值，不是recommend/update输入。

仓库中已运行的例子位于`next_experiment/demo/`；试验建议卡可直接阅读，不必重新运行。

## 用自己的观测逐步操作

复制演示中的case.json，确认模型、噪声、允许输入与单位，再提供观测。以下命令使用已附演示数据展示完整接口：

```sh
feasibility/.venv/bin/python next_experiment/cli.py recommend \
  --case next_experiment/demo/case.json \
  --observations next_experiment/demo/observations.json \
  --output /tmp/next-test-recommendation

feasibility/.venv/bin/python next_experiment/cli.py update \
  --case next_experiment/demo/case.json \
  --observations next_experiment/demo/observations.json \
  --measurement next_experiment/demo/measurement.json \
  --output /tmp/next-test-update
```

实际观测JSON格式：

```json
{
  "records": [
    {"id": "run-001", "experiment": "initial", "values_K": [307.528247414709]}
  ]
}
```

追加数据文件只包含一个record，不再套records：

```json
{
  "id": "run-002",
  "experiment": "heat_high",
  "values_K": [330.9116860666025, 341.9402539878528, 348.427009565167]
}
```

数组顺序严格对应case中该试验的observations。普通热试验是绝对K；reference是“传感器读数−独立参考读数”的K差值，可以为负。ID必须唯一，不允许重复提交同一个观测。不同ID复用同一物理测量仍会重复计数，软件不能自动识别，需用户保证每条记录是独立试验。

`update`只追加数据并计算新后验，不暗中开始下一次实验。若仍有歧义，可将新`observations.json`再传给`recommend`。budget是每次建议可用额度，**不是自动维护的累计试验账本**；完成实验后应由用户更新剩余额度与enabled选项。`update`要求新记录所对应实验已启用且不超当前预算，但不强迫必须执行上一建议；替代试验也可以更新判断。

## 可修改的任务定义

- `priors`：两个候选解释的先验概率，必须为正并合计1。
- `grid.convection`和`grid.offset_K`：对应解释内的离散参数支持。
- `grid.gain`和`grid.capacity`：两个解释共有的吸收功率增益与热容量干扰参数，不以固定为真值来人为简化任务。
- `experiments`：每项的enabled、声明cost、噪声sigma_K、输入节点、三分区功率和观测时刻/位置。
- `budget`：下一试验的可用成本额度。cost是用户声明资源单位，不自动把时长/能耗合并成评分。
- `max_predicted_temperature_K`：全参数网格、离散求解时间上的物理温度筛选（不含传感器偏置）；默认演示380K，**不是沿用旧优化任务的360K，也不是经过设备批准的上限**。改成360K会排除默认高功率试验，应依自己的安全设计定义。
- `assumptions.independent_reference_available`：只有显式设为true且reference.enabled=true、cost≤budget时，独立参考试验才可能被推荐。

每次实验必须独立从296.15K均温开始；本版不支持拿“刚做完上一个试验的热状态”直接当新初态。不允许超出适配器定义的几何/时间/噪声/功率范围，具体错误会返回退出码2。模拟功率是模型假设下的吸收功率乘已声明gain，不等同设备电功率。

候选解释只覆盖这两类机制：真实情况可能同时存在散热变化、零偏、漂移、初温误差等。本版不会自动发现第三种根因。请求数据必须能映射到现有模型，否则应扩建受验证的适配器，而非仅改JSON宣称通用。

## 如何理解输出

| 状态 | 意义 |
|---|---|
| `experiment_recommended` | 有满足可用性、成本、预测温度筛选的试验，预计信息增益≥0.01nat |
| `ambiguous` | 更新后仍没有任何候选达到0.95相对支持 |
| `supported_hypothesis` | 在当前两个有限网格候选内有≥0.95支持；不是根因确认、实物置信度或安全结论 |
| `unsupported` | 两个候选网格不能解释联合记录或至少一条新增记录；应检查候选范围、噪声/测量/模型结构 |
| `not_distinguishable` | 允许试验预计模型信息增益太低；不能用一个最高分强行推荐 |
| `no_available_experiment` | 无启用且预算/预测温度筛选通过的候选；没有凭空追加参考测量 |

全部状态保持`engineering_release=not_supported`。预测区间是有限粒子与假定噪声产生的5/95分位，未进行实际覆盖率校准。后验接近1可能来自过窄网格或错误噪声假设；ESS很低时更应警惕粒子近似不足。

`best_grid_fit_tail_probability`只是保守的不适配筛查：在拟合网格中先选最好残差再算chi-square尾概率，不是经过参数选择校正的统计显著性。未被拒绝不代表模型集合完整。

## 验证和小规模对照

```sh
feasibility/.venv/bin/python -B -m unittest discover -s next_experiment -p 'test_*.py' -v
feasibility/.venv/bin/python -B next_experiment/verify_demo.py
```

`verify_demo.py`调用独立CLI recommend/update并验证重复数据被拒绝，重算16对象×4策略的更新结果。`evaluate.py`是正式对照运行脚本，已有evaluation目录时拒绝覆盖，重跑前先归档。它不是普通快速单元测试的一部分。

本轮对照没有显示信息增益策略胜过简单分离度启发式。更多结果和限制见RESULTS.md。此原型的价值首先是一个具体任务的完整流程，不应包装成已有用户或AI创新成果。
