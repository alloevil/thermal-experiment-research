# 独立最小环境与异地证据副本验证

## 本轮推进

报告生成不再需要安装完整39包科学计算环境。本轮新增`requirements-report.in`及带发行文件哈希的`requirements-report.lock`，仅包含`numpy==2.5.3`。没有升级或移除原环境的依赖，没有改写旧阶段清单或数据。

新增`tools/verify_isolated_report.py`，通过显式`--allow-install`授权执行一次临时环境安装与复现。普通`workbench.py list/check/report`仍不安装依赖，普通单元测试也不访问网络。

## 实际执行步骤与结果

1. 核验原八阶段1186个清单条目，拒绝在快照损坏时启动复制。
2. 将清单内文件、八份清单及workbench/test_workbench两个入口文件复制到含中文和空格的新路径，共1196个文件。没有复制旧`.venv`、任意其他未记录文件或通过软链接指回原工作区。
3. 通过Python标准库venv创建`system_site_packages=False`、`with_pip=False`的空环境。使用`-I -B`子进程，确认第三方包清单为空且NumPy不可导入。
4. 在不同工作目录运行副本的list/check：无需科学依赖也成功，1186条目全部匹配。
5. 在空环境尝试report：退出码2、stdout为空，明确提示缺少NumPy。不是模拟该失败分支。
6. 显式执行uv，指定PyPI、禁用uv配置及缓存，`--require-hashes --only-binary :all:`安装锁定依赖。新环境里唯一的已安装发行包是NumPy 2.5.3，模块路径在新环境内部。
7. 在同一副本中生成JSON、Markdown和`python -O`报告，分别与此前冻结的输出逐字一致，所有报告仍为`engineering_release=not_supported`。
8. 副本中运行原17项workbench测试和14项evidence_report测试，31项全部通过。这没有运行其他科学模型测试或解ODE。
9. 比较复制目录执行前后的文件集合、内容、大小和mtime：1196文件未变，未新增/删除文件；原工作区固定快照也保持不变。
10. 临时副本和环境退出时自动删除，持久化保存安装、包来源、命令、测试与结果日志。

## 运行证据

主日志：`tools/results/isolated-report-audit.log`。

```text
PASS fresh venv has zero packages; copied list/check work; report rejects missing NumPy
PASS isolated install contains only hash-locked NumPy 2.5.3; import originates inside the venv
PASS relocated JSON/Markdown/-O reports are byte-identical; 17 entrypoint and 14 report tests pass
PASS 1196 relocated files unchanged; original pinned stages unchanged; temporary venv/copy removed
```

详细证据目录：`tools/results/isolated-report/`。

| 文件 | 证明范围 |
|---|---|
| `empty-environment.stdout.txt` | 新环境初始发行包为空、NumPy不可导入，prefix与base_prefix不同 |
| `report-missing-numpy.stderr.txt` | 真实缺依赖路径返回失败提示 |
| `install.stderr.txt` | 安装解析/下载/安装单个NumPy包 |
| `installed-environment.stdout.txt` | 安装后仅有NumPy 2.5.3 |
| `numpy-origin.stdout.txt` | NumPy模块确实来自临时环境 |
| `report-json.stdout.txt` / `report-markdown.stdout.txt` | 实际重新生成的报告 |
| `workbench-tests.stderr.txt` / `evidence-tests.stderr.txt` | 在副本和新环境中的17+14项测试结果 |
| `commands.json` | 实际命令、显式安装参数及退出码 |
| `receipt.json` | 文件数量、大小、环境版本、锁文件哈希和范围限制 |

本次主审计约16.01秒。按普通文件逻辑大小计算，复制证据约227.87 MB，新虚拟环境约150.91 MB（十进制）；不是下载流量、实际块占用或跨平台性能指标。安装日志报告NumPy下载约15.9 MiB，与展开后的环境大小不是同一概念。

## 审计工具本身的测试

新增6项标准库测试：

- 仅复制清单文件与明确入口，排除原虚拟环境和未记录文件。
- 源快照损坏时不开始复制。
- 已存在目标目录不覆盖。
- 未提供`--allow-install`时不启动子进程。
- 清除继承的PYTHONPATH、PYTHONHOME、VIRTUAL_ENV和Conda路径变量，不原地修改父进程环境。
- 最小锁中只有一个版本固定且带哈希的NumPy依赖。

加上原17项入口测试，本地标准库测试共23项通过。日志：`tools/results/isolated-audit-tests.log`。这23项和副本中的31项有重叠，不能相加冒称54项独立覆盖。

## 重跑

```sh
python -B -S -m unittest discover -s tests -p 'test_*.py' -v
python -B -S tools/verify_isolated_report.py --allow-install
```

主审计会写入`tools/results/isolated-report/`，如已存在则拒绝覆盖。重跑前先归档旧目录，不要删除不理想记录后假装首次运行。脚本有网络安装行为，只在显式授权参数存在时执行；超时或失败保留已经写出的日志，不自动重试安装或修改版本。

首次使用的最小环境安装见根目录QUICKSTART.md。本轮没有保留一个额外长期运行的`.venv-report`，需要时按指南自行创建。

## 严格限制

- **同平台隔离，不是另一台机器。** 实测Linux x86_64、CPython 3.12.8（conda-forge基础解释器）；仍共享宿主系统库、内核和基础Python。没有验证Windows/macOS、Python其他版本或无系统库环境。
- `-I`及新venv隔离的是Python路径和包，不是容器/网络/进程沙箱。不能以该审计证明对不可信代码的安全隔离。
- **报告复现，不是科学重算。** 轻量环境没有SciPy、PyTorch或py-pde，不能运行完整建模/拟合实验。报告本身仍需已有的数组与日志证据。
- **清单复制，不是完整开发仓库。** 副本用于固定报告和测试，可能不包含历史阶段所有上游源码、图像、未记录文件或许可证附件。它不是已经审核可公开发布的分发包。
- **哈希锁不等于来源认证。** 本次安装接受锁文件中的发行文件哈希，保证安装文件与该锁匹配；锁与所有代码仍需可信。本轮没有软件供应链签名认证或许可证兼容性审查。
- 原科学环境仍为39包、未改动。最小报告环境仅减少查阅/报告所需依赖，不提升模型真实性、校准精度或工程可靠性。

下一步应优先验证面向外部使用的完整资料边界和最小可复现实验，而不是把成功生成报告当作项目已完成或具备工业价值。
