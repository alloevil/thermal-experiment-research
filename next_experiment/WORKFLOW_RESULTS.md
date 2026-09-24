# 三层协同工作流：本轮运行结果

日期：2026-09-24。范围：通用热系统的开发案例与本地研究数据审核，不是实际半导体设备、真实用户审批或新算法评测。

## 改了什么

- A 层复用原有有限网格信息增益推荐，不改变原算法、对照实验或其未胜过简单启发式的结论。
- B 层复用原有热方程预测与观测适配器，没有新训练的代理模型或工业数字孪生。
- C 层新增 `workflow.py`，支持跨进程 plan/review/observe，保存完整提案、审核记录、观测更新、工具事件及本次预算。
- 新增 `demo_workflow.py`，默认停在待审核；显式 `--approve-simulation` 才生成下一次模拟观测并推进。没有调用 LLM 或设备接口。

## 实际执行命令

以下从工作区根目录执行；重跑时更换输出目录，程序拒绝覆盖已有结果。

```sh
TZ=UTC PYTHONDONTWRITEBYTECODE=1 \
  research/thermal-ai4engineering/feasibility/.venv/bin/python -B \
  research/thermal-ai4engineering/next_experiment/demo_workflow.py \
  --output research/thermal-ai4engineering/next_experiment/workflow_run \
  --approve-simulation
```

plan、review、observe 是三个独立 Python 进程，均实际退出 0。完整子命令及输出保存在 [commands.log](workflow_run/commands.log)。审核者标注 `simulation-demo-opt-in`，只是显式模拟许可，不是真实工程师身份或生产审批。

## 重新计算的开发演示

| 项目 | 本轮实际结果 |
|---|---|
| 初始状态 | ambiguous |
| 初始候选相对支持 | convection 0.511609；offset 0.488391 |
| 推荐实验 | heat_high |
| 新模拟读数 | 330.911686、341.940254、348.427010 K |
| 更新状态 | supported_hypothesis，候选内支持 convection |
| 有限粒子 ESS | 约1.0063，提示强烈集中，不应解读成物理根因确定 |
| 工作流状态 | completed |
| 本次声明预算 | before=1，spent=1，remaining=0 |
| 工程放行 | not_supported |
| 单次演示墙钟 | 9.5687秒，含子进程；仅记录，不与旧耗时作性能比较 |

本轮重新执行了初始与后续观测的96单元仿真，但沿用旧开发对象/种子。不是新独立任务，也没有新增工业数据。新后验与旧开发案例逐字段一致，说明编排没有改变本例数值结果，不代表所有输入均已验证。

环境：Python 3.12.8、NumPy 2.5.3、SciPy 1.18.1，复用原虚拟环境，没有安装依赖。完整输出在 [result.json](workflow_run/result.json)，人工阅读入口在 [完成报告](workflow_run/completed/report.md)。

## 测试与拒绝证据

```sh
TZ=UTC PYTHONDONTWRITEBYTECODE=1 \
  research/thermal-ai4engineering/feasibility/.venv/bin/python -B -m unittest discover \
  -s research/thermal-ai4engineering/next_experiment -p 'test_*.py' -v
```

本轮共26项测试通过，含原11项及新增15项；最终运行日志为 [tests.log](workflow_run/tests.log)。覆盖：

- 原数值/输入约束与24/96单元检查，新增更新结果和原后验一致。
- 无审核、缺少研究用途确认、错误提案/实验、审核否决、提案或模型改变。
- 重复观测、非有限值、缺失数据来源、完成状态重复提交。
- 等价候选、预算不足、温度筛选及候选外观测；拒绝或不适配不被吞掉。
- 含空格/中文路径、不同工作目录、独立CLI进程续接、拒绝覆盖。
- 演示未提供模拟许可时，只生成待审核提案，没有新增测量或审核文件。

另对真实 plan 快照执行未审核 observe 请求，实际结果：

```text
exit_code=2
Request rejected: Observation requires an approved, unfinished proposal
```

未创建失败请求的输出目录。三个成功子命令均未接收隐藏真值文件路径；结果见 [verification.log](workflow_run/verification.log)。这是所执行路径的检查，不是系统隔离或对抗恶意输入的安全证明。

## 旧成果保护

- 本轮开始时保存的76个既有模型、推荐代码与产物文件，结束时SHA-256均未变。
- `workbench.py check` 对已有八阶段快照校验通过；它只核对完整性，没有重跑旧科学实验。日志见 [archive-check.log](workflow_run/archive-check.log)。
- 更新根与研究目录的共识，并补充入口链接；没有改写旧算法或旧基准结论。

## 尚未完成与风险

- C 层是确定性工具编排，不是具有自然语言规划能力的 LLM Agent；本轮没有模型服务、训练或代理模型加速。
- 自声明审核没有身份认证；提案摘要不是签名或防恶意篡改机制。旧批准快照可另开分支，预算与去重只作用于本条结果链。
- 数据来源标签不证明测量真实性；实际初温、传感器校准、模型完整性和连续时空安全均未获证明。
- 暂未接内部数据、真实工程师或实际设备；未证明算法增量、用户价值、工艺收益或生产可靠性。

使用说明见 [WORKFLOW.md](WORKFLOW.md)。下一步应让具体工程师核对输入、允许试验和输出是否有用，而非仅增加更多编排功能。
