# Thermal Experiment Research

**热模型与测量不一致时，下一次该测什么？**

**Thermal Experiment Research** 是一个面向**热建模（thermal modeling）、参数校准（parameter calibration）和实验设计中的模型辨别（model discrimination）**的 Python 完整研究仓库。现有原型从允许的试验中选择下一步，帮助区分散热变化与测温零偏。热方程检查、受限加热、失败反例、原始观测与执行日志一起保留，不只展示成功结果。

[English](README.md) · [运行原型](#运行原型) · [研究导航](#研究导航) · [常见问题](#常见问题) · [引用说明](CITATION.md)

![研究流程：建模、选择试验、审查证据。新观测也可能否定候选解释。](assets/readme/research-flow.svg)

**这是研究原型，不是设备控制器或工业数字孪生。** 下一试验演示使用合成系统；新增的[TCLab实测样例研究](real_data/tclab/RESULTS.md)回放了作者公开测量数据，但不等于我们独立完成硬件验证、企业合作或 AI 优势证明。

## 已能运行的闭环

现有原型比较“散热变化”和“测温零偏”，同时保留吸收功率增益、热容量的不确定性：

1. 输入任务与已有观测。
2. 更新有限参数集合下的候选支持度。
3. 从启用且满足声明预算的试验中推荐下一步，或明确弃权。
4. 先记录研究用途审核，再接收新增观测。
5. 更新判断，保留“仍有歧义”“候选都不适配”等结果，绝不自动工程放行。

![实际合成演示：初始候选支持度、允许试验的信息增益，以及新增观测后的更新。](next_experiment/demo/decision.png)

[查看完整图](next_experiment/demo/decision.png) · [阅读已生成的试验建议卡](next_experiment/demo/recommendation.md) · [查看工作流完成报告](next_experiment/workflow_run/completed/report.md)

记录中的初始两候选约为 **51%／49%**，程序推荐 `heat_high`，新增模拟观测后转向支持散热变化。把预测温度上限收紧到 360 K 则改选 `cooldown`。这些是有限模型内的判断，**不是经认证的概率、根因确认或安全操作指令**。

## 运行原型

只查阅与检查文件完整性时，Python 标准库即可：

```sh
python workbench.py list
python workbench.py check
```

运行原型使用 Python 3.12 与已有的双包锁。若没有 uv，请先[显式安装](https://docs.astral.sh/uv/getting-started/installation/)：

```sh
python3.12 -m venv --without-pip .venv
uv pip install --python .venv/bin/python --require-hashes --only-binary :all: \
  -r requirements-thermal.lock

# 默认停在待审核提案，不自行生成下一次观测。
.venv/bin/python next_experiment/demo_workflow.py --output /tmp/thermal-review

# 明确同意模拟，完整运行 plan → review → observe。
.venv/bin/python next_experiment/demo_workflow.py \
  --output /tmp/thermal-simulated-loop --approve-simulation
```

每次使用新的输出路径，程序拒绝覆盖。这里没有任何设备连接；模拟审核者只是标签，不是身份认证或生产审批。已实测 Linux x86_64 / CPython 3.12.8，其他平台需要另验。

[任务和观测格式](next_experiment/GUIDE.md) · [独立审核／录入命令](next_experiment/WORKFLOW.md)

## 结果包含什么，也不证明什么

| 发现 | 证据与限制 |
|---|---|
| 训练拟合更好不代表后续预测更好 | 作者提供的双加热器样例中，独立模型在前300秒拟合更好，但后半段RMSE高于耦合模型；只有一个历史序列，不是主动试验效果验证。[实测案例](real_data/tclab/RESULTS.md) |
| 试验选择闭环可运行 | 独立进程完成推荐、审核和新增观测，保留拒绝与歧义。[工作流记录](next_experiment/WORKFLOW_RESULTS.md) |
| 复杂选择方法没有获胜 | 16 个合成案例中，信息增益与简单分离度都明确判断 13 个、保留 3 个；固定冷却的 Brier 略好。[策略对照](next_experiment/RESULTS.md) |
| 小残差仍会漏报 | 增加诊断后仍有 5 个预测不达标案例未告警，数值精化未消除反例。[偏置边界](bias_boundary/RESULTS.md) |
| 参考会传递自身误差 | 参考偏高 0.35 K 时，4 个校正预测仍不达标且未告警。[参考校正](reference_correction/RESULTS.md) |
| 校准在指定前提下有用 | 有效参数比值校准改善同结构合成模型的留出预测，不能恢复绝对尺度或证明实物可靠。[校准结果](calibration/RESULTS.md) |

样本数量不是现场故障概率。重复噪声、共享观测、有限网格和噪声假设均有说明，不把各阶段计数拼成宣传用“大规模基准”。

需要简洁且可追溯的项目定义、方法和边界，请看[项目事实索引](docs/PROJECT_FACTS.md)。引用某个数值时，应指向具体研究及其协议，不只引用仓库名称。

## 研究导航

| 目录／阶段 | 要回答的问题 |
|---|---|
| 文献与产品方向 | [已有工作是什么？](report.md) · [谁可能使用它？](PRODUCT_DIRECTION.md) |
| `feasibility/` | [上游案例能否复现，数值解是否收敛？](feasibility/RESULTS.md) |
| `radiation/` | [非线性辐射与功率限制下能否优化加热？](radiation/RESULTS.md) |
| `sensitivity/` | [标称方案对哪些参数敏感，哪些参数不可辨识？](sensitivity/RESULTS.md) |
| `calibration/` | [有效比值校准能否改善留出预测？](calibration/RESULTS.md) |
| `model_mismatch/` | [拟合收敛能否暴露未知模型／测量错误？](model_mismatch/RESULTS.md) |
| `bias_boundary/` | [小偏置下告警在哪里漏报？](bias_boundary/RESULTS.md) |
| `reference_correction/` | [一点参考校正何时帮助、何时误导？](reference_correction/RESULTS.md) |
| `next_experiment/` | [下一试验选择](next_experiment/GUIDE.md) · [审核工作流](next_experiment/WORKFLOW.md) |
| `evidence_report/`、`tools/` | [如何报告而不暗示安全？](evidence_report/RESULTS.md) · [如何独立重算？](tools/THERMAL_REPLAY_RESULTS.md) |

各目录保留协议与结果；`sources/`、`product_research/`提供出处、原始抓取哈希与来源说明，不再分发第三方全文。历史开发输出、失败尝试和合成数据仍完整保留。[公开版引用处理](docs/REFERENCE_POLICY.md) · [迁移记录](docs/ARCHIVE.md)。

## 检查不等于重算

```sh
# 标准库：迁移清单、固定快照与入口测试。
python scripts/check.py --quick

# 增加证据报告、原型／工作流和新数组验收测试。
.venv/bin/python scripts/check.py

# 真正执行一遍新的热方程与优化，写入新目录。
python tools/replay_thermal.py --python .venv/bin/python \
  --output /tmp/thermal-scientific-replay
```

CI 定义使用同一个完整检查命令，不重跑所有历史实验、不自动生成图片，也不认证物理准确性。部分旧验证脚本会写入记录或图片，先阅读对应阶段说明再运行。[复现指南](docs/REPRODUCE.md)。

## 适用边界与下一步

现有模型采用教学参数和合成观测。试验适配器只处理两类候选机制，依赖有限网格、已知初始均温与独立高斯噪声。参考可用性必须明确声明，但程序无法自动证明它准确。所有输出保持 **`engineering_release=not_supported`**。

下一步需要具体研究者／工程师的公开或授权模型失配案例，而不是继续增加通用 Agent。当前没有外部采用、企业需求或 AI 优势证明。[贡献指南](CONTRIBUTING.md)。

## 常见问题

### 能上传任意 CSV 自动诊断设备吗？

不能。当前适配器需要 JSON 任务、已知测量位置／时间和声明的噪声，使用仓库内的热模型及两类候选机制，不从任意 CSV 自动推断设备物理。具体见[输入格式](next_experiment/GUIDE.md)。

### 是否使用大模型、强化学习或自主科学家？

没有。当前下一试验原型使用有限参数集合的贝叶斯更新和信息增益估计，审核层是确定性编排。研究方向属于 AI4Engineering，但没有证明 AI 相对经典方法的优势。详见[实际策略对照](next_experiment/RESULTS.md)。

### 是否替代 BayBE、Pyomo.DoE 或 do-mpc？

不是。这是保留失败反例的受限热研究案例，不是通用实验设计或控制框架。[同类工具调研](PRODUCT_DIRECTION.md#3-实际查到的已有工作)列出已有能力与重叠，不是对这些软件运行后的性能排名。

### 没有 GPU 和实验设备也能运行吗？

可以运行合成下一试验工作流和热模型重算，它们在 CPU 上使用 NumPy／SciPy，不需要模型 API 密钥或设备连接。模拟审核不代表真实实验批准。参见[复现说明](docs/REPRODUCE.md)和[引用／来源说明](CITATION.md)。

## 许可与发布

**尚未选择覆盖原创部分的开源许可证，公开可见不等于新增许可。** 公开版不上传第三方论文二进制，引用正文改为出处说明；保留的 py-pde／BoTorch 可执行示例附带 MIT 声明。[第三方边界](THIRD_PARTY.md)与[发布记录](docs/PUBLICATION.md)说明了处理方式；不声称已有本项目论文、DOI 或软件包发行版。
