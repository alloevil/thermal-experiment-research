# 统一入口验收记录

## 交付

- 根目录`workbench.py`：标准库实现的`list`、`check`，以及显式调用旧报告器的`report`。
- 根目录`QUICKSTART.md`：区分查阅、快照检查、数组报告和会写入结果的科学重算。
- `tests/test_workbench.py`：标准库单元/集成测试，不需要NumPy。
- `tools/verify_workbench.py`：真实报告环境下的端到端只读审计。

没有新增科学依赖、运行新拟合、重新生成旧图片或修改前八阶段快照。入口不会替用户自动选择虚拟环境、安装依赖、刷新pin或执行所有实验。

## 运行证据

执行：

```sh
python -B -S -m unittest discover -s tests -p 'test_*.py' -v
python -B -S tools/verify_workbench.py
```

单元/集成测试17项通过，日志：`tools/results/workbench-tests.log`。覆盖：

- 有效快照、内容改动、文件缺失、重写清单但保留旧pin。
- JSON重复键、非有限/溢出数字、无效摘要、重复条目及条目计数错误。
- 路径穿越、绝对路径、文件及阶段目录符号链接。
- 单个阶段损坏使整体invalid，并在启动报告子进程前停止。
- 缺NumPy时不启动报告、不安装依赖；报告器失败时丢弃部分stdout，不冒充成功。
- 标准库模式从其他工作目录启动；`python -O`不绕过校验；未知stage退出码2。

真实集成记录：`tools/results/workbench-integration.log`。

```text
PASS standard-library list/check from unrelated cwd; all 1186 pinned entries matched
PASS python -O retains checks; invalid stage exits 2 with no report
PASS real JSON/Markdown report forwarding matches prior outputs; no release assertion
PASS 1223 prior-stage files unchanged in content, size and mtime; no added/removed files
```

报告在已存在的`feasibility/.venv`中实际运行，JSON和Markdown均与前一阶段报告完全一致。未将“NumPy缺失”仅停留在文字提醒，测试通过模拟缺失分支确认不会继续执行报告器；该项不是在新机器上安装测试。

## 怎样理解数字

- 1186：八阶段固定清单的条目总数。部分是重复来源、日志或派生文件，不是独立实验次数。
- 1223：本次只读审计遍历的旧阶段文件数量，还包含清单外文件。比较内容SHA-256、大小、mtime及文件集合；不检查访问时间、不包含虚拟环境，不等于恶意代码沙箱或零副作用的形式化证明。
- 17：本轮入口测试数量，不是旧科学实验测试全集。

## 安全与科学边界

快照摘要固定在本地入口代码中，属于可信代码的本地记录，不提供签名或来源认证。若入口代码、清单及数据同时被替换，校验无法证明原始真实性。科学重算必须按原协议执行，不能以文件哈希一致代替重新验证数值、参数适用性或设备行为。

`check`只验证文件完整性；`report`还重算第七阶段保存数组的部分指标，仍不执行ODE或验证参考证书。任何路径都不会产生工程放行结果。当前没有`run-all`，以避免隐藏重算/覆盖行为。

后续可独立验证干净环境和对外分享路径；当前成果尚未发布为软件包，也没有外部研究者或设备厂采用证据。长期完善目标保持进行中。
