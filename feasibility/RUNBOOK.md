# 复现与检查

所有命令在本目录运行。原始调研保留在上一级；本目录不是已发布软件包。

## 环境

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python \
  --index https://download.pytorch.org/whl/cpu \
  --index-strategy unsafe-best-match -r requirements.lock
uv pip check --python .venv/bin/python
```

依赖锁定 39 个包，使用 CPU PyTorch，不下载 CUDA 运行时。正常复查现有结果无需再次安装；本目录已有虚拟环境。脚本将 BLAS/OpenMP/Numba 线程设为 1。

## 上游资料

```sh
.venv/bin/python scripts/fetch_sources.py
```

该命令重新获取固定 commit 的源码与许可并更新获取时间。上游原文件不修改；原始 SHA-256 记录在 `upstream/manifest.json`。执行前自动检查文件哈希。

## 原生案例

```sh
set -o pipefail
timeout 240s .venv/bin/python -u scripts/run_upstream.py heat 2>&1 | tee logs/upstream-heat-rerun.log
timeout 420s .venv/bin/python -u scripts/run_upstream.py botorch 2>&1 | tee logs/upstream-botorch-rerun.log
```

结果 JSON 和热场图会重新生成。py-pde 原生随机示例的默认随机源保持原状，因此其图像和精确均值可能变化；三项边界测试和 BoTorch 使用已记录种子。

BoTorch 使用上游 `SMOKE_TEST=1`，不是完整参数实验。原生 EI 数值警告保留，不修补或把该对照当成正式算法排名。

## 热模型

```sh
timeout 900s .venv/bin/python -u scripts/thermal_probe.py 2>&1 | tee logs/thermal-rerun.log
```

已有同配置 `thermal-raw.jsonl` 时跳过完成项，这条命令用于断点续跑，不是重新测量全部时间。正式结果来自修复标准差指标后的一次完整进程，160 次测量没有跨进程拼接。

如需全新测量，应先将旧的 `results/thermal-*.json` 和 `results/thermal-raw.jsonl` 移入新的归档子目录，再运行同一命令。保留旧结果，不覆盖或删除后冒称第一次运行。

`--pilot` 可运行 1 个工况、4 档网格的小预检；只有 1 个工况时不计算排序相关性。

## 绘图和验收

```sh
.venv/bin/python scripts/plot_results.py
.venv/bin/python scripts/verify_results.py
```

验收检查源码哈希、原生案例结果、160 条记录的工况配对、均值守恒、时间误差、空间收敛与协议哈希，并生成当前产物的哈希清单。它不是第三方代码的完整 CI，也不是独立求解器交叉验证。

若重新生成任何结果文件，请重新运行验收命令，更新 `results/artifact-manifest.json`；旧版汇总报告中的计时不会自动更新，应以新原始记录为准。

## 失败记录

- `logs/thermal-pilot.log`：初次传入求解器实例失败；该版本要求类或注册名称。修复后见 `logs/thermal-pilot-fixed.log`。
- `logs/metric-bug-reproduction.log`：复现 py-pde 的 fluctuations 与普通标准差不同。两档网格的普通标准差均为 0.5，但 fluctuations 分别为 0.03125 和 0.015625。
- `results/attempt-1/`：首轮及早期预检数据，只为保留审计轨迹；非最终有效数据，非最终结论来源。
- `logs/thermal-measurement.log`：首轮日志；`logs/thermal-measurement-final.log` 才是修正指标后的完整正式运行。

## 限制

数学问题是无热源、绝热边界的二维扩散，不包含加热控制、辐射、腔壁、晶圆材料参数或实物数据。四档网格都是数值近似，解析解负责数学验收；不得将其包装为某厂商设备数字孪生。
