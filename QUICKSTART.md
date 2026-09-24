# 从这里开始：热工程研究工作台

本项目研究“热模型、校准与诊断在什么条件下值得信任”，目前只有公开方程上的合成实验。**不是半导体设备数字孪生、自动控制产品或工程放行系统。**

这份文档介绍现有研究资产的运行方式，不是最终产品定义。当前优先任务和同类工具对照见[PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md)：先验证模型失配后的下一次试验决策，不继续无限扩展验证工具。

## 先试产品原型：推荐下一次试验

```sh
feasibility/.venv/bin/python next_experiment/cli.py demo --output /tmp/next-test-demo
```

这会真正执行候选模型比较、推荐允许试验、生成一条模拟新观测并更新判断，同时演示无法区分与候选外拒绝。新目录必须不存在，结果不写入旧实验。核心仅依赖NumPy/SciPy；可用已安装的`.venv-thermal/bin/python`替代解释器。

查看已生成的[试验建议卡](next_experiment/demo/recommendation.md)、[输入/更新接口指南](next_experiment/GUIDE.md)与[对照结果](next_experiment/RESULTS.md)。当前只支持已有热模型的两个候选机制，不是任意CSV或设备的自动诊断。

最重要的结果不是“优化器能收敛”，而是：小残差也可能漏报错误预测；可靠参考能校正稳定零偏，但错误参考会制造假信心。完整进度与每阶段结果见[STATUS.md](STATUS.md)。

## 三种操作，先分清

| 想做什么 | 入口 | 是否运行科学计算 | 是否改写旧产物 |
|---|---|---|---|
| 看有哪些阶段 | `python workbench.py list` | 否；只是目录 | 否 |
| 检查文件是否与保存的快照一致 | `python workbench.py check` | 否；只重算哈希 | 否 |
| 重新生成证据说明 | `feasibility/.venv/bin/python workbench.py report` | 重算保存数组上的指标，不解ODE/拟合 | 否；报告发往stdout |
| 轻量重算辐射加热案例 | `tools/replay_thermal.py --python ... --output ...` | 是；数值检查、一次优化和新场验收 | 只写入指定的全新目录 |
| 重做某阶段实验或原数值检查 | 按对应阶段RUNBOOK/RESULTS操作 | 可能运行ODE、拟合、绘图 | **可能**；先读归档/断点说明 |

`check`通过只代表文件完整性，不是科学实验通过、来源真实性或设备安全。没有`run-all`命令，避免把数小时实验或结果覆盖隐藏在一个“检查”按钮后面。

## 第一次查阅：只需要Python 3.10+

在本目录（`research/thermal-ai4engineering`）运行：

```sh
python workbench.py list
python workbench.py check
python workbench.py check reference_correction --json
```

前两条不需要NumPy/PyTorch，也不需要激活虚拟环境。目录中必须存在旧阶段的数据和清单；缺失数据将返回错误，不会下载或悄悄忽略。

这些命令不依赖当前工作目录，亦可从其他位置调用`python /完整路径/workbench.py check`。路径相对于脚本位置解析，不将终端当前目录误认为研究目录。

当前固定8个阶段，共1186个清单条目；报告会逐阶段显示`matched_snapshot`或`invalid`。阶段之间可能包含重复来源或派生产物，**1186不是独立实验数量，也不涵盖清单外所有文件**。

## 查看证据，而不是只看PASS

无需任何环境也可直接阅读已经保存的[参考证据报告](evidence_report/results/reference-evidence.md)。如需现场重新核算：

```sh
feasibility/.venv/bin/python workbench.py report --format markdown
feasibility/.venv/bin/python workbench.py report --format json
```

`report`先核对全部8阶段快照，再用当前Python解释器的NumPy执行固定的报告器。使用隔离模式和禁止字节码写入，不自动选择其他Python、不安装包。如果当前解释器没有NumPy，退出码为2，提示使用已有虚拟环境。

输出保留四层边界：

- 完整性：文件是否和固定快照相同，不能证明谁生成了它。
- 可观测信息：拟合状态、残差、参考样本和随机标准误差，不含隐藏物理真值。
- 仿真回顾：隐藏预测误差与漏报，只能在合成研究评价端计算。
- 缺失前提：参考溯源、独立均温证据、校正温区/有效期、漂移界和硬件验证。

所有报告保持`engineering_release=not_supported`。即使无告警、拟合成功或隐藏误差为0，也不会自动放行。

如果要保存新报告，请选择清单之外的新位置，并检查退出码：

```sh
feasibility/.venv/bin/python workbench.py report --format json > /tmp/thermal-evidence.json
```

shell重定向可能在命令失败时留下空文件；不能以“文件存在”作为成功依据。不要重定向到旧快照文件，否则下次`check`会正确报告变化。

## 环境缺失怎么办

先使用标准库`list/check`以及已保存报告。**只生成证据报告，无需安装39包科学环境**：现已验证仅含NumPy 2.5.3的独立环境。以下命令在本目录执行，使用Python 3.12和已有uv：

```sh
python3.12 -m venv --without-pip .venv-report
uv --no-config pip install --python .venv-report/bin/python \
  --require-hashes --only-binary :all: --index-url https://pypi.org/simple \
  -r requirements-report.lock
.venv-report/bin/python workbench.py report --format markdown
```

没有uv时需先自行安装它；工作台不会自动安装任何依赖。别把`.venv-report`指向已有科学环境，保持它们独立。Windows解释器路径不同，以上shell命令只在当前Linux环境验证；Python 3.10可用于标准库目录/快照检查，但没有验证NumPy 2.5.3在该版本上的安装。

实测在同一Linux x86_64主机新建空环境，只安装1个包，并将全部固定快照移到不含原`.venv`的中文/空格路径；JSON/Markdown与原报告逐字相同，31项复制后的测试通过。该验证仍使用同一系统/基础Python，不等同另一台机器或不同OS。[隔离复现证据](tools/ISOLATED_REPORT_RESULTS.md)。

报告专用NumPy环境不支持科学重算。若只想重算辐射加热案例，可用下一节的NumPy/SciPy双包环境；需要其他历史实验（例如BoTorch）时，仍按[第一阶段环境说明](feasibility/RUNBOOK.md)安装原39包锁定环境。

## 真正重算一个科学案例：只需NumPy和SciPy

以下操作会执行新的ODE积分、数值收敛检查和一次SLSQP优化，不是读取旧的结果。已在本机全新CPython 3.12环境实际验证：

```sh
python3.12 -m venv --without-pip .venv-thermal
uv --no-config pip install --python .venv-thermal/bin/python \
  --require-hashes --only-binary :all: --index-url https://pypi.org/simple \
  -r requirements-thermal.lock
python tools/replay_thermal.py --python .venv-thermal/bin/python \
  --output /tmp/my-thermal-replay
```

`/tmp/my-thermal-replay`必须不存在，且不能位于任何旧归档阶段内。命令验证旧源码快照，复制原模型、原数值检查、原优化程序与协议；旧实验JSON仅作为单独的比较参考，不放入新`results/`冒充重算结果。

运行器只支持锁定的NumPy 2.5.3/SciPy 1.18.1，不会自行安装或更换解释器。每个阶段最多240秒，失败保留该新目录内日志并返回2；重试须保留旧记录并选择新目录，不静默覆盖。

新输出包含原协议的数值检查、18步左右的单次优化（不保证所有平台迭代数相同）、96单元温度场、功率/热量和`results/replay-verification.json`。独立验收器从新数组重算MSE、温度与功率限制及热量收支，并与冻结参考按提前声明的容差比较。

**不包含**全部校准、敏感性、BoTorch、绘图或硬件验证，也不支持将结果视为新算法收益。当前只有同Linux/Python平台上的隔离复现证据，跨OS需要另验。[科学重算记录](tools/THERMAL_REPLAY_RESULTS.md)。

## 选择一个问题深入

| 问题 | 阅读入口 | 原复算说明 |
|---|---|---|
| 数值解是否收敛、算一次多贵？ | [数值复现结果](feasibility/RESULTS.md) | [运行说明](feasibility/RUNBOOK.md) |
| 功率约束与辐射怎么处理？ | [受限加热结果](radiation/RESULTS.md) | 同文件“重跑与断点” |
| 参数变了，标称方案还有效吗？ | [参数敏感性](sensitivity/RESULTS.md) | 同文件“产物与重跑” |
| 校准前如何处理不可辨识性？ | [有效比值校准](calibration/RESULTS.md) | [运行说明](calibration/RUNBOOK.md) |
| 拟合成功能否代表可信？ | [未知偏差结果](model_mismatch/RESULTS.md) | 同文件“重跑” |
| 哪些小偏置会被告警漏掉？ | [偏置边界](bias_boundary/RESULTS.md) | [运行说明](bias_boundary/RUNBOOK.md) |
| 参考自身不准怎么办？ | [参考校正结果](reference_correction/RESULTS.md) | [运行说明](reference_correction/RUNBOOK.md) |
| 如何表达证据与缺失前提？ | [证据报告](evidence_report/RESULTS.md) | [运行说明](evidence_report/RUNBOOK.md) |

## 测试统一入口

```sh
python -B -S -m unittest discover -s tests -p 'test_*.py' -v
```

测试包含标准库离线启动、其他工作目录、错误pin、缺失/篡改、符号链接、重复/无效清单和报告转发失败。测试对临时目录做修改，不改旧实验结果。真实报告器的测试另见evidence_report/RUNBOOK.md。

已有完整虚拟环境时，可进一步运行`python -B -S tools/verify_workbench.py`，核对真实JSON/Markdown转发和旧阶段文件只读行为。它不会执行科学重算；运行证据见[统一入口验收记录](tools/WORKBENCH_RESULTS.md)。

希望重做隔离安装审计时，可运行`python -B -S tools/verify_isolated_report.py --allow-install`。该命令会显式从PyPI下载锁定wheel到临时环境、复制证据、运行31项复制测试，并在结束后删除临时环境和副本。结果写入`tools/results/isolated-report/`，若已有结果则拒绝覆盖；先审查并归档旧目录。普通单元测试不执行网络安装。

## 快照不匹配时

1. 不要自动更新`workbench.py`内的pin，也不要删除报错阶段。
2. 先区分缺失文件、意外改写与有意重新实验。旧绘图或验证脚本也可能重新写文件。
3. 保存和审查新旧差异；确认新的实验、验收及范围后，再显式记录新快照。这不是本命令的自动功能。

当前pin只是本地研究快照的固定记录，不是密码学签名；同时篡改工作台源码和所有清单的行为不在检测保证内。运行环境和本地代码需可信。本工具不隔离不可信Python解释器或巨型恶意输入，也不验证实际证书。

## 当前仍未完成

项目还缺独立物理审查、真实参考溯源与温区/漂移证据、外部用户复用及实际设备数据。统一入口解决的是“怎么看、怎么核对、怎么避免误执行”，不是新增工业真实性或算法优势。
