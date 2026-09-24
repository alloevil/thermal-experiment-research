# 独立参考校正实验：执行说明

在本目录执行，复用已存在的`../feasibility/.venv`及锁定依赖。

```sh
set -o pipefail
../feasibility/.venv/bin/python check_correction.py | tee logs/check-rerun.log
timeout 600s ../feasibility/.venv/bin/python -u run.py 2>&1 | tee logs/run-rerun.log
../feasibility/.venv/bin/python -u verify.py 2>&1 | tee logs/verify-rerun.log
```

## 行为与断点

主实验已完成时不再次拟合；已完成案例从case.json读取。未完成拟合只有调用日志时，原fit_ratios拒绝静默重启，需要先显式归档该分支再重新运行。协议/源码/上游依赖哈希变动会拒绝混跑，须先归档整个results目录。

完成后重新运行verify.py会重算对象0/噪声0全部8个最终拟合预测、能量收支和各项指标，不会根据效果重拟合。检查器生成的图、verification.json及日志改变后应重新保存产物哈希。

## 文件

- correction.py：小型纯计算接口。estimate_offset只接受两组同步K读数；apply_offset验证通道数、非有限值与正绝对温度，不原地修改。
- check_correction.py：确定性算术、参考偏差传递与10项无效输入检查。
- results/config.json：预设对象、场景和协议/代码/依赖哈希。
- results/object-N：真实无偏物理场，所有观测分支共用。
- noise-R-S/readings.npz：加热前传感器/参考读数、raw与corrected标定/诊断观测。
- offset.json：零偏估计、样本数、样本标准差和均值标准误差；后者不是总测量不确定度。
- raw及corrected目录：冻结拟合、告警、残差、预测与评分。未校正分支并未获得校正后的额外信息。
- refinement.json及refined.npz：预定案例和所有校正漏报的精化；alarm96.npz是漏报案例的更细告警残差。
- logs/run.log：完整调用过程，数值警告不屏蔽。

## 使用边界

这里模拟的10次平衡参考测量不是实际校准证书。给校正器一个系统有偏的参考，会把偏差传给所有校正后温度；增加读数次数不能保证消除这个系统误差。当前没有参考自诊断、漂移识别或传感器灵敏度修正。

两分支使用同一观测、拟合算法和预算，但校正分支多用了10个参考及30个传感器平衡读数。任何收益结论必须同时说明这笔资源和“已均温”的前提，不得称为无成本改进。
