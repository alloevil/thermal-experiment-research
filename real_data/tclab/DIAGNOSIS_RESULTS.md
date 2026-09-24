# 实测记录诊断结果

本轮解决一个具体问题：**拟合前，判断记录是否根本没有包含某路加热增益的信息。** 不重新拟合、不生成故障标签，不证明主动试验推荐收益。

## 同一记录的三个前缀

输入为[原作者提供的599行样例](upstream/data.txt)，SHA256为`10278caee2b095cca028e19acd9146157a75cdd8426e0490231de7a9def8ebdc`。时序遵循先测温、再施加该行输入；末行指令不计入已观测激励。

|选择窗口|行数 / 区间数|末次观测 s|Q2非零观测时长 s|Q2输入积分 %·s|结论|
|---|---:|---:|---:|---:|---|
|t < 100|100 / 99|99.027058|0|0|alpha2缺输入信息|
|t < 101|101 / 100|100.027688|0|0|末行Q2=50%，但无后续观测；仍缺信息|
|t < 300|300 / 299|299.268678|199.240990|9962.049508|严格零输入障碍消失，未证明可辨识|

保存的实际输出：[100秒JSON](diagnosis_examples/before-100.json)、[100秒中文卡片](diagnosis_examples/before-100.md)、[101秒JSON](diagnosis_examples/before-101.json)、[300秒JSON](diagnosis_examples/before-300.json)。积分是控制指令的时间积分，不是热量。

## 下一步如何使用

- 若目标是估计alpha2，前100秒数据不足，不能把优化器返回的默认值当估计结果。
- 对101秒前缀，优先查找末行指令生效后的已有测量；没有这些观测时，追加同一末行不能弥补信息缺口。
- 对300秒前缀，转入参数灵敏度、测量噪声及模型范围检查；本规则不自动推荐再做一次试验。
- 若确实需要补测，必须由操作者明确允许的幅值、变化率、温度限制、观测时长和起始条件。本工具不提供设备执行指令，也不把历史指令视作安全范围。

## 实际验证

以下命令从仓库根执行，不需要科学计算依赖：

```sh
python -B -S -m unittest discover -s real_data/tclab -p 'test_diagnose.py' -v
python -B -S real_data/tclab/diagnose.py \
  --data real_data/tclab/upstream/data.txt --before-seconds 101 --format json
```

本次运行摘要：

```text
Ran 14 tests
OK
PASS t<100: rows=100 intervals=99 missing=['alpha2'] Q2_integral=0.000000000 percent-seconds terminal_change=False
PASS t<101: rows=101 intervals=100 missing=['alpha2'] Q2_integral=0.000000000 percent-seconds terminal_change=True
PASS t<300: rows=300 intervals=299 missing=[] Q2_integral=9962.049508095 percent-seconds terminal_change=False
PASS independent Decimal interval arithmetic; JSON/Markdown CLI snapshots match
PASS all 50 previously tracked TCLab files unchanged before navigation edits
```

独立核验从原CSV以Decimal解析并累加每个左端输入×实际时间差，与报告按`rel_tol=1e-12, abs_tol=1e-10`比较；另核对保存报告与独立CLI逐字节一致。50个旧文件比较发生在本轮RUNBOOK导航更新之前，未重跑或覆盖历史拟合。完整本地日志位于`output/tclab-diagnosis/`，按仓库规则不发布。

测试覆盖恒定非零、同步输入、极小非零、末行变化、不等时间间隔、单位/数值拒绝及跨目录只读执行。这里的“通过”仅指声明的输入契约和零输入规则，不是完整可辨识性、模型正确性或工业安全验证。

仓库级复核也已运行：`TZ=UTC /tmp/thermal-research-packaging/venv/bin/python -B scripts/check.py`退出0，五组共104项测试通过（33+14+26+6+25），8个历史阶段的1186项清单记录与固定快照一致。该解释器是本机已有NumPy/SciPy环境；其他机器应按仓库锁文件准备环境。25个本轮文档中的本地链接有效，除RUNBOOK导航外49个既有TCLab文件与HEAD逐字节一致。`git diff --check`通过；`gitleaks dir real_data/tclab --no-banner --redact`和`gitleaks git . --no-banner --redact`均报告`no leaks found`。这些检查不等于完整科学重跑或第三方安全审计。
