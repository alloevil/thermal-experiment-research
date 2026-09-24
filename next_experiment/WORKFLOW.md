# A+B+C：带显式审核的单任务研究闭环

本版处理已有通用热系统中“对流变化还是测温零偏”的下一次辨别试验。不是任意配方优化器、真实半导体设备模型或通用自主 Agent。

## 三层能力

| 层 | 本版实际能力 | 未实现或未证明 |
|---|---|---|
| A 实验选择 | 复用 core.py 的有限网格后验和信息增益排序、拒绝推荐出口 | 没有新增算法；旧对照未显示它胜过简单分离度启发式 |
| B 物理预测 | 复用热方程求解器、参数集合与含噪预测区间 | 不训练代理模型；区间未经实物覆盖率校准，不是工业数字孪生 |
| C 工具编排 | plan/review/observe 状态转换、独立进程续接、提案审核与证据报告 | 无 LLM、自然语言自主规划、设备接口或身份认证 |

未新增依赖。使用已有 NumPy/SciPy 环境；不使用可能有版本冲突的系统 Python。

## 一条命令重跑完整模拟

在 `research/thermal-ai4engineering` 下运行：

```sh
TZ=UTC PYTHONDONTWRITEBYTECODE=1 feasibility/.venv/bin/python -B \
  next_experiment/demo_workflow.py --output /tmp/thermal-workflow-demo --approve-simulation
```

去掉 `--approve-simulation` 会停在待审核，不生成下一次模拟观测。显式许可只适用于本次教学模拟，不代替真实工程师审核。演示通过三个独立 CLI 进程串联，完整命令与返回码写入 `commands.log`；初始数据和新观测重新计算，但使用既有开发对象/种子，不是新增独立评测集。

仿真真值保存在独立 `simulation-truth.json`，不传入计划、审核或观测更新命令。中断时各步骤已保存的会话可按下面命令继续，不需要重跑已完成的步骤。

## 逐步运行

在 `research/thermal-ai4engineering` 下运行。以下使用既有模拟案例，不是实际企业数据。所有输出目录必须不存在；改名可保留每次结果。

```sh
PYTHON=feasibility/.venv/bin/python

"$PYTHON" -B next_experiment/workflow.py plan \
  --case next_experiment/demo/case.json \
  --observations next_experiment/demo/observations.json \
  --output /tmp/thermal-workflow-plan
```

plan 只计算候选与建议，不生成新测量，不执行实验。阅读 `/tmp/thermal-workflow-plan/report.md`，核对实验输入、观测、预算、假设与模型限制。若返回 `no_action`，保留其具体原因，不进入审核。

读取提案 ID，显式决定是否同意录入该实验的研究数据。下面的 `heat_high` 仅适用于附带模拟案例；更换任务后必须核对实际推荐。

```sh
PROPOSAL_ID=$("$PYTHON" -c 'import json; print(json.load(open("/tmp/thermal-workflow-plan/session.json"))["proposal_id"])')

"$PYTHON" -B next_experiment/workflow.py review \
  --session /tmp/thermal-workflow-plan/session.json \
  --proposal-id "$PROPOSAL_ID" --experiment heat_high \
  --decision approve --reviewer simulation-review \
  --acknowledge-research-only \
  --output /tmp/thermal-workflow-review
```

不认可建议时使用 `--decision reject` 并选择新的输出目录。审核操作不调用求解器或测量工具。`simulation-review` 只是演示标签，不代表真实工程师身份或生产审批。

在外部完成研究测量或仿真后，显式声明数据来源并录入。该工作流不读取仿真真值、不自行生成测量。

```sh
"$PYTHON" -B next_experiment/workflow.py observe \
  --session /tmp/thermal-workflow-review/session.json \
  --measurement next_experiment/demo/measurement.json \
  --origin simulated \
  --output /tmp/thermal-workflow-result
```

这条示例使用旧模拟观测来演示续接。新增观测格式沿用 [GUIDE.md](GUIDE.md)；只有审批的实验可以进入此次结果链。自行提供的经授权研究数据用 `user_supplied_research`，标签不是来源真实性认证，也不证明现有热模型适用该数据。

## 输出与状态

每一步写入独立的 `session.json` 和 `report.md`，不修改输入或前一步文件。会话内保存原始任务、已有观测、两候选预测、提案、审核和工具事件，进程退出后通过 `--session` 继续。

| 状态 | 意义 | 下一步 |
|---|---|---|
| pending_review | 已有建议，未审核 | 审核同一提案和实验 |
| no_action | 不可辨别、无可用实验、候选不适配或已有充分相对支持 | 看具体原因，不强行审核 |
| approved | 已记录研究用途同意 | 录入匹配实验的新增观测 |
| rejected | 审核否决 | 不接受观测；修改任务后另建提案 |
| completed | 已记录观测并更新候选支持 | 阅读 posterior；completed 不等于模型可信或工艺成功 |

在所有状态中 `engineering_release=not_supported`。新观测使两候选都不适配时，结果仍为 `unsupported`，不为了闭环成功而隐藏失败；本次实验成本仍记入。

## 审核和预算边界

- 审核绑定提案 ID、实验及原始模型源码指纹。改动输入、建议或模型后必须重新计划与审核。
- 摘要用于发现不一致，不是数字签名、用户认证、不可篡改审计或对抗恶意编辑的安全机制。
- 本版不验证实际设备执行、初始温度、仪器有效性或同意者身份，不能用作生产安全关卡。
- 本次预算为建议时额度减去一次声明成本；已有历史数据成本不计入，非时间/能耗优化。
- 对完成状态再次提交会被拒绝，但重新使用旧 approved 快照可另建结果分支。本地无全局账本或跨分支去重；不能用于真实设备任务调度。
- 不自动推荐下一轮或循环执行。剩余额度、独立起始状态及下一步任务需操作者确认。
- 预测温度只是有限网格与离散时刻筛选，不能证明连续时间或真实设备安全。

## 验证

```sh
TZ=UTC PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B -m unittest discover \
  -s next_experiment -p 'test_*.py' -v
```

测试包含原 11 项数值/输入检查及新工作流的审核绑定、提案变动、模型变动、重复观测、错误实验、来源声明、拒绝/不适配、原后验一致和跨进程 CLI。

本轮运行证据及结果见 [WORKFLOW_RESULTS.md](WORKFLOW_RESULTS.md)。不沿用旧对照数字冒充本轮新算法评测。
